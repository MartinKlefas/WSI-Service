import asyncio
import os
import pathlib

import aiohttp
from fastapi import HTTPException

from wsi_service.models.v1.slide import SlideInfo as SlideInfoV1
from wsi_service.models.v3.slide import SlideInfo as SlideInfoV3
from wsi_service.plugins import load_slide
from wsi_service.singletons import logger
from wsi_service.utils.slide_utils import ExpiringSlide, LRUCache


class SlideManager:
    def __init__(self, mapper_address, data_dir, timeout, cache_size):
        self.mapper_address = mapper_address
        self.data_dir = data_dir
        self.timeout = timeout
        self.storage_mapper = {}
        self.slide_cache = LRUCache(cache_size)
        self.lock = asyncio.Lock()
        self.storage_locks = {}
        self.event_loop = asyncio.get_event_loop()

    async def get_slide(self, slide_id, plugin=None):
        if slide_id in self.storage_mapper:
            storage_address = self.storage_mapper[slide_id]
        else:
            main_storage_address = await self._get_slide_main_storage_address(slide_id)
            storage_address = os.path.join(self.data_dir, main_storage_address["address"])
            self.storage_mapper[slide_id] = storage_address

        logger.debug("Storage address for slide %s: %s", slide_id, storage_address)

        cache_id = storage_address
        if plugin:
            cache_id = storage_address + f" ({plugin})"

        await self._set_storage_lock(cache_id)

        exp_slide = self.slide_cache.get_item(cache_id)
        if exp_slide is None:
            async with self.storage_locks[cache_id]:
                slide = await load_slide(storage_address, plugin=plugin)
                exp_slide = ExpiringSlide(slide)
                removed_item = self.slide_cache.put_item(cache_id, exp_slide)
                if removed_item:
                    removed_item[1].timer.cancel()
                    await removed_item[1].slide.close()
                logger.debug("New slide handle opened for storage address: %s", storage_address)

        self._reset_slide_expiration(cache_id, exp_slide)

        try:  # check if slide is up-to-date and update if supported
            await exp_slide.slide.refresh()
        except AttributeError:
            pass

        return exp_slide.slide

    async def get_slide_info(self, slide_id, slide_info_model, plugin=None):
        slide = await self.get_slide(slide_id=slide_id, plugin=plugin)
        slide_info = await slide.get_info()
        # overwrite dummy id with actual slide id
        slide_info.id = slide_id
        # slide info conversion
        slide_info = self._convert_slide_info_to_match_slide_info_model(slide_info, slide_info_model)
        if isinstance(slide_info, SlideInfoV3):
            # set and extend slide format identifier
            if not slide_info.format:
                slide_info.format = ""
            if "file" not in slide_info.format and "folder" not in slide_info.format:
                if os.path.isfile(slide.filepath):
                    slide_info.format = "file-" + pathlib.Path(slide.filepath).suffix[1:] + "-" + slide_info.format
                elif os.path.isdir(slide.filepath):
                    slide_info.format = "folder-" + slide_info.format
            if slide.plugin not in slide_info.format:
                if slide_info.format and not slide_info.format.endswith("-"):
                    slide_info.format += "-"
                slide_info.format += f"{slide.plugin}"
            slide_info.format = slide_info.format.lower()
            # enable raw download if filepath exists on disk
            if os.path.exists(slide.filepath):
                slide_info.raw_download = True
        return slide_info

    async def get_slide_file_paths(self, slide_id):
        storage_addresses = await self._get_slide_storage_addresses(slide_id)
        return [os.path.join(self.data_dir, s["address"]) for s in storage_addresses]

    def close(self):
        for cache_id, slide in self.slide_cache.get_all().items():
            slide.timer.cancel()
            self._sync_close_slide(cache_id)

    async def _set_storage_lock(self, cache_id):
        async with self.lock:
            if cache_id not in self.storage_locks:
                self.storage_locks[cache_id] = asyncio.Lock()

    def _reset_slide_expiration(self, cache_id, expiring_slide):
        if expiring_slide.timer is not None:
            expiring_slide.timer.cancel()
        expiring_slide.timer = self.event_loop.call_later(self.timeout, self._sync_close_slide, cache_id)
        logger.debug("Set expiration timer for storage address (%s): %s", cache_id, self.timeout)

    async def _get_slide_storage_addresses(self, slide_id):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.mapper_address.format(slide_id=slide_id)) as r:
                    if r.status == 404:
                        raise HTTPException(
                            status_code=404, detail=f"Could not find a storage address for slide id {slide_id}."
                        )
                    slide = await r.json()
        except aiohttp.ClientConnectorError:
            raise HTTPException(
                status_code=503, detail="WSI Service is unable to connect to the Storage Mapper Service."
            )
        return slide["storage_addresses"]

    async def _get_slide_main_storage_address(self, slide_id):
        storage_addresses = await self._get_slide_storage_addresses(slide_id)
        for storage_address in storage_addresses:
            if storage_address["main_address"]:
                return storage_address
        return storage_addresses[0]

    def _sync_close_slide(self, cache_id):
        asyncio.create_task(self._close_slide(cache_id))

    async def _close_slide(self, cache_id):
        if self.slide_cache.has_item(cache_id):
            exp_slide = self.slide_cache.pop_item(cache_id)
            await exp_slide.slide.close()
            logger.debug("Closed slide with storage address: %s", cache_id)

    def _convert_slide_info_to_match_slide_info_model(self, slide_info, slide_info_model):
        if issubclass(slide_info_model, SlideInfoV1):
            if isinstance(slide_info, SlideInfoV3):
                # v3 --> v1
                slide_info_dict = slide_info.dict()
                del slide_info_dict["format"]
                del slide_info_dict["raw_download"]
                slide_info = SlideInfoV1.parse_obj(slide_info_dict)
        if issubclass(slide_info_model, SlideInfoV3):
            if isinstance(slide_info, SlideInfoV1):
                # v1 --> v3
                slide_info = SlideInfoV3.parse_obj(slide_info.dict())
        return slide_info
