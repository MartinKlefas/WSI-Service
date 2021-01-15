# WSI Service

## Overview



The *WSI Service* enables users to stream Whole Slide Images (WSI) tile-based via HTTP. It is based on a FastAPI webserver and OpenSlide to access whole slide image data.

Regarding the slide's metadata, it provides the extent of the base level (original image, level=0), its pixel size in nm (level=0), general tile extent, the total count of levels and a list of levels with information about its extent, downsampling factor (2^level) in relation to the base level and a generated flag which indicates if the level is part of the original data or if it is generated by the WSI Service.

<img src="https://upload.wikimedia.org/wikipedia/commons/thumb/4/43/Image_pyramid.svg/1024px-Image_pyramid.svg.png" alt="CC BY-SA 3.0" width="200"/>

Regions of the WSI can be requested on any of the available levels. There is also a way to access tiles of a predefined size of each level (e.g. useful for a [viewer](wsi_service/viewer.html)). Furthermore, it is possible to get a thumbnail, label and macro image.

There are several endpoints made available by this service:

* `GET /slides/{slide_id}/info` - Get slide info, e.g.
```json
{
    "id": "f863c2ef155654b1af0387acc7ebdb60",
    "extent": {
        "x": 46000,
        "y": 32914,
        "z": 1
    },
    "num_levels": 16,
    "pixel_size_nm": {
        "x": 499.0,
        "y": 499.0,
        "z": None
    },
    "tile_extent": {
        "x": 256,
        "y": 256,
        "z": 1
    },
    "levels": [
    {
      "extent": {
        "x": 46000,
        "y": 32914,
        "z": 1
      },
      "downsample_factor": 1,
      "generated": false
    },
    {
      "extent": {
        "x": 23000,
        "y": 16457,
        "z": 1
      },
      "downsample_factor": 2,
      "generated": true
    },
```
[...]
```json
    {
      "extent": {
        "x": 1,
        "y": 1,
        "z": 1
      },
      "downsample_factor": 32768,
      "generated": true
    }
  ]
}
```
* `GET /slides/{slide_id}/region/level/{level}/start/{start_x}/{start_y}/size/{size_x}/{size_y}?image_format=jpeg&image_quality=90&z=0` - Get slide region: Get region of the slide. Level 0 is highest (original) resolution. Each level has half the resolution and half the extent of the previous level. Coordinates are given with respect to the requested level.
* `GET /slides/{slide_id}/tile/level/{level}/tile/{tile_x}/{tile_y}?image_format=jpeg&image_quality=90&z=0` - Get slide tile: Get tile of the slide. Extent of the tile is given in slide metadata. Level 0 is highest (original) resolution. Each level has half the resolution and half the extent of the previous level. Coordinates are given with respect to tiles, i.e. tile coordinate n is the n-th tile in the respective dimension.
* `GET /slides/{slide_id}/thumbnail/max_size/{max_x}/{max_y}?image_format=jpeg&image_quality=90` - Get slide thumbnail image
* `GET /slides/{slide_id}/label?image_format=jpeg&image_quality=90` - Get slide label image
* `GET /slides/{slide_id}/macro?image_format=jpeg&image_quality=90` - Get slide macro image

The last five endpoints all return image data. The image format and its quality (e.g. for jpeg) can be selected. Formats include jpeg, png, tiff, bmp, gif. The region and the tile endpoint also offer the selection of a layer with the index z in a Z-Stack.

### Standalone version

The WSI Service relies on the [Storage Mapper Service](https://gitlab.cc-asp.fraunhofer.de/empaia/platform/data/storage-mapper-service) to get storage information for a certain slide_id. If the mapper-address is not provived (see *How to run*), the WSI Service will be run in standalone mode using a local mapper. This local mapper fulfills the function of the storage mapper service, the id mapper service and part of the clinical data service by creating case ids for folders found in the data folder and slide ids for images within these case folders. In the standalone mode there are few additional endpoints, which can be accessed:

* `GET /cases/` - Get cases
* `GET /cases/{case_id}/slides/` - Get available slides
* `GET /slides/{slide_id}` - Get slide
* `GET /slides/{slide_id}/storage` - Get slide storage information

There is also a simple viewer, which can be used by accessing: http://localhost:8080/slides/{slide_id}/viewer

## How to run
WSI Service is a python module and can be run either locally or via docker.

### Run locally
Make sure [OpenSlide](https://openslide.org/download/) and [Poetry](https://python-poetry.org/) is installed. Install WSI Service by running the following lines within this folder
```
cd wsi_service
poetry install
poetry shell
```

Make sure that libpixman is on version 0.40.0 or later to prevent broken MRXS files. (such as by defining (and installing)  `LD_PRELOAD=/usr/local/lib/libpixman-1.so.0.40.0` on older os versions).

Start via
```
python3 -m wsi_service [OPTIONS] data_dir

positional arguments:
  data_dir             Base path to histo data

optional arguments:
  -h, --help           Show this help message and exit
  --port PORT          Port the WSI Service listens to
  --debug              Use the debug config
  --load-example-data  This will download an example image into the data
                       folder before starting the server
  --mapper-address     Mapper-Service Address
```
Afterwards, visit http://localhost:8080

### Run with docker
Download the turnkey ready docker image
```
docker pull registry.gitlab.cc-asp.fraunhofer.de:4567/empaia/platform/data/wsi-service
```

or build the docker image yourself from source
```
cd PATH_OF_DOCKERFILE
docker build -t registry.gitlab.cc-asp.fraunhofer.de:4567/empaia/platform/data/wsi-service .
```
Of course, it can be tagged e.g. with only *wsi-service*, here the tag is just used for consistency with following commands.

Run the docker image (Caution: ~13GB of example data will be downloaded):
```
docker run -it --rm -p 8080:8080 registry.gitlab.cc-asp.fraunhofer.de:4567/empaia/platform/data/wsi-service --load-example-data
```

Or with more options
```
docker run \
  -it \
  -p 8080:8080 \
  --rm \
  -v PATH_TO_DATA_DIR_ON_HOST:/data \
  -v PATH_TO_REPOSITORY_ROOT:/wsi_service \
  registry.gitlab.cc-asp.fraunhofer.de:4567/empaia/platform/data/wsi-service \
  --debug
```

Short explanation of the parameters used:

* ```-it``` initializes an interactive tty
* ```-p 8080:8080``` forward the port
* ```--rm``` optional, remove if container should be reused (recommended)
* ```-v PATH_TO_DATA_DIR_ON_HOST:/data``` optional, if not set, empty dir will be used. Make sure container user (-u) has read access
* ```-v PATH_TO_REPOSITORY_ROOT:/wsi_service``` optional, will use the source code of host and automatically restart server on changes
* ```--debug``` optional, use debug config and activate reload

Afterwards, visit http://localhost:8080


## Development

### Use debug to activate reload

Service is reloaded after code changes. Activate locally with
```
poetry shell
python3 -m wsi_service --debug data_dir
```
or using docker with
```
docker run \
  -it \
  -p 8080:8080 \
  --rm \
  -v PATH_TO_DATA_DIR_ON_HOST:/data \
  -v PATH_TO_REPOSITORY_ROOT:/wsi_service \
  registry.gitlab.cc-asp.fraunhofer.de:4567/empaia/platform/data/wsi-service \
  --debug
```

### Run tests 
```
poetry run pytest --pyargs wsi_service
```
or using docker with
```
docker run \
  -it \
  --rm \
  --entrypoint python3 \
  registry.gitlab.cc-asp.fraunhofer.de:4567/empaia/platform/data/wsi-service \
  -m pytest --pyargs wsi_service
```

### Run static code analysis and fix issues

If you are using VS Code there are already default [settings](https://gitlab.cc-asp.fraunhofer.de/empaia/platform/data/wsi-service/-/blob/master/.vscode/settings.json) that will sort your imports and reformat the code on save. Furthermore, there will be standard pylint warnings from VS Code that should be fixed manually.

To start the automatic formatter from console run
```
black .
```

To start the automatic import sorter from console run
```
isort . --profile black
```

To start pylint from console run
```
pylint wsi_service --disable=all --enable=F,E,unreachable,duplicate-key,unnecessary-semicolon,global-variable-not-assigned,unused-variable,binary-op-exception,bad-format-string,anomalous-backslash-in-string,bad-open-mode --extension-pkg-whitelist=pydantic
```
following [VS Code](https://code.visualstudio.com/docs/python/linting#_default-pylint-rules).
