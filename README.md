# cjio, or CityJSON/io

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/tudelft3d/cjio/blob/master/LICENSE)
[![](https://badge.fury.io/py/cjio.svg)](https://pypi.org/project/cjio/)

Python CLI to process and manipulate [CityJSON](http://www.cityjson.org) files.
The different operators can be chained to perform several processing operations in one step, the CityJSON model goes through them and different versions of the CityJSON model can be saved as files along the pipeline.


## Installation

It uses Python 3.5+ only.

To install the latest release:

```console
pip install cjio
```

To install the development branch, and still develop with it:

```console
git checkout develop
virtualenv venv
. venv/bin/activate
pip install --editable .
```

Alternatively, you can use the included Pipfile to manage the virtual environment with [pipenv](https://pipenv.readthedocs.io/en/latest/).

**Note for Windows users**

If your installation fails based on a *pyproj* or *pyrsistent* error there is a small hack to get around it.
Based on the python version you have installed you can download a wheel (binary of a python package) of the problem package/s.
A good website to use is [here](https://www.lfd.uci.edu/~gohlke/pythonlibs).
You then run:

```console
pip3 install [name of wheel file]
```

You can then continue with:

```console
pip3 install cjio
```

## Docker

If docker is the tool of your choice, please read the following hints.

To run cjio via docker simply call:

```console
docker run --rm  -v <local path where your files are>:/data tudelft3d/cjio:latest cjio --help
```

To give a simple example for the following lets assume you want to create a geojson which represents 
the bounding boxes of the files in your directory. Lets call this script *gridder.py*. It would look like this:

```python
from cjio import cityjson
import glob
import ntpath
import json
import os
from shapely.geometry import box, mapping

def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)

files = glob.glob('./*.json')

geo_json_dict = {
    "type": "FeatureCollection",
    "features": []
}

for f in files:
    cj_file = open(f, 'r')
    cm = cityjson.reader(file=cj_file)
    theinfo = json.loads(cm.get_info())
    las_polygon = box(theinfo['bbox'][0], theinfo['bbox'][1], theinfo['bbox'][3], theinfo['bbox'][4])
    feature = {
        'properties': {
            'name': path_leaf(f)
        },
        'geometry': mapping(las_polygon)
    }
    geo_json_dict["features"].append(feature)
    geo_json_dict["crs"] = {
        "type": "name",
        "properties": {
            "name": "EPSG:{}".format(theinfo['epsg'])
        }
    }
geo_json_file = open(os.path.join('./', 'grid.json'), 'w+')
geo_json_file.write(json.dumps(geo_json_dict, indent=2))
geo_json_file.close()
```

This script will produce for all files with postfix ".json" in the directory a bbox polygon using cjio and save the complete geojson result in grid.json in place.

If you have a python script like this, simply put it inside your 
local data and call docker like this:

```console
docker run --rm  -v <local path where your files are>:/data tudelft3d/cjio:latest python gridder.py
```

This will execute your script in the context of the python environment inside the docker image.

## Usage

After installation, you have a small program called `cjio`, to see its possibities:

```console
cjio --help

Commands:
  assign_epsg                Assign a (new) EPSG.
  compress                   Compress a CityJSON file, ie stores its...
  decompress                 Decompress a CityJSON file, ie remove the...
  export                     Export the CityJSON to another format.
  extract_lod                Extract only one LoD for a dataset.
  info                       Output info in simple JSON.
  locate_textures            Output the location of the texture files.
  merge                      Merge the current CityJSON with others.
  remove_duplicate_vertices  Remove duplicate vertices a CityJSON file.
  remove_materials           Remove all materials from a CityJSON file.
  remove_orphan_vertices     Remove orphan vertices a CityJSON file.
  remove_textures            Remove all textures from a CityJSON file.
  reproject                  Reproject the CityJSON to a new EPSG.
  save                       Save the city model to a CityJSON file.
  subset                     Create a subset of a CityJSON file.
  update_bbox                Update the bbox of a CityJSON file.
  update_textures            Update the location of the texture files.
  upgrade_version            Upgrade the CityJSON to the latest version.
  validate                   Validate the CityJSON file: (1) against its...
```


## Pipelines of operators

The 3D city model opened is passed through all the operators, and it gets modified by some operators.
Operators like `info` and `validate` output information in the console and just pass the 3D city model to the next operator.

```console
$ cjio example.json subset --id house12 info remove_materials info save out.json
$ cjio example.json remove_textures compress info
$ cjio example.json upgrade_version save new.json
$ cjio myfile.json merge '/home/elvis/temp/*.json' save all_merged.json
```


## Validation of CityJSON files against the schema

To validate a CityJSON file against the [schemas of CityJSON](https://github.com/tudelft3d/cityjson/tree/master/schema) (this will automatically fetch the schemas for the version of CityJSON):

```console
$ cjio myfile.json validate
```

If the file is too large (and thus validation is slow), an option is to crop a subset and just validate it:

```console
$ cjio myfile.json subset --random 2 validate
```

If you want to use your own schemas, give the folder where the master schema file `cityjson.json` is located:

```console
$ cjio example.json validate --folder_schemas /home/elvis/temp/myschemas/
```


## Example CityJSON datasets

There are a few [example files on the CityJSON webpage](https://www.cityjson.org/datasets/).

Alternatively, any [CityGML](https://www.citygml.org) file can be automatically converted to CityJSON with the open-source project [citygml-tools](https://github.com/citygml4j/citygml-tools) (based on [citygml4j](https://github.com/citygml4j/citygml4j)).


