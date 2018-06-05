
import os
import sys
import re

import json
import collections
import jsonref
import urllib
from pkg_resources import resource_filename
import copy
import random


from cjio import validation
from cjio import subset


def reader(file, ignore_duplicate_keys=False):
    return CityJSON(file=file, ignore_duplicate_keys=ignore_duplicate_keys)

def off2cj(file):
    l = file.readline()
    # print(l)
    while (len(l) <= 1) or (l[0] == '#') or (l[:3] == 'OFF'):
        l = file.readline()
        # print(l)
        # print ('len', len(l))
    numVertices = int(l.split()[0])
    numFaces    = int(l.split()[1])
    lstVertices = []
    for i in range(numVertices):
        lstVertices.append(list(map(float, file.readline().split())))
    lstFaces = []
    for i in range(numFaces):
        lstFaces.append(list(map(int, file.readline().split()[1:])))
    cm = {}
    cm["type"] = "CityJSON"
    cm["version"] = "0.6"
    cm["CityObjects"] = {}
    cm["vertices"] = []
    for v in lstVertices:
        cm["vertices"].append(v)
    g = {'type': 'Solid'}
    shell = []
    for f in lstFaces:
        shell.append([f])
    g['boundaries'] = [shell]
    g['lod'] = 1
    o = {'type': 'GenericCityObject'}
    o['geometry'] = [g]
    cm["CityObjects"]["id-1"] = o
    return CityJSON(j=cm)



class CityJSON:

    def __init__(self, file=None, j=None, ignore_duplicate_keys=False):
        if file is not None:
            self.read(file, ignore_duplicate_keys)
            self.path = os.path.abspath(file.name)
        elif j is not None:
            self.j = j
        else: #-- create an empty one
            self.j = {}
            self.j["type"] = "CityJSON"
            self.j["version"] = "0.6"
            self.j["CityObjects"] = {}
            self.j["vertices"] = []

    def __repr__(self):
        return self.get_info()


    def get_version(self):
        return self.j["version"]


    def get_epsg(self):
        if "metadata" not in self.j:
            return None
        if "crs" in self.j["metadata"] and "epsg" in self.j["metadata"]["crs"]:
            return self.j["metadata"]["crs"]["epsg"]
        elif "referenceSystem" in self.j["metadata"]:
            s = self.j["metadata"]["referenceSystem"]
            return int(s[s.find("::")+2:])
        else:
            return None


    def is_empty(self):
        if len(self.j["CityObjects"]) == 0:
            return True
        else:
            return False

    def read(self, file, ignore_duplicate_keys=False):
        if ignore_duplicate_keys == True:
            self.j = json.loads(file.read())
        else:
            try:
                self.j = json.loads(file.read(), object_pairs_hook=validation.dict_raise_on_duplicates)
            except ValueError as err:
                raise ValueError(err)
        #-- a CityJSON file?
        if "type" in self.j and self.j["type"] == "CityJSON":
            pass
        else:
            self.j = {}
            raise ValueError("Not a CityJSON file")

            
    def fetch_schema(self):
        #-- fetch proper schema
        v = self.j["version"].replace('.', '')
        try:
            schema = resource_filename(__name__, '/schemas/v%s/cityjson.json' % (v))
        except:
            return (False, None)
        #-- open the schema
        fins = open(schema)
        jtmp = json.loads(fins.read())
        fins.seek(0)
        if "$id" in jtmp:
            u = urllib.urlparse(jtmp['$id'])
            os.path.dirname(u.path)
            base_uri = u.scheme + "://" + u.netloc + os.path.dirname(u.path) + "/" 
        else:
            abs_path = os.path.abspath(os.path.dirname(schema))
            base_uri = 'file://{}/'.format(abs_path)
        js = jsonref.loads(fins.read(), jsonschema=True, base_uri=base_uri)
        return (True, js)


    def fetch_schema_cityobjects(self):
        #-- fetch proper schema
        v = self.j["version"].replace('.', '')
        try:
            schema = resource_filename(__name__, '/schemas/v%s/cityjson.json' % (v))
        except:
            return (False, None)
        sco_path = os.path.abspath(os.path.dirname(schema))
        sco_path += '/cityobjects.json'
        jsco = json.loads(open(sco_path).read())
        return (True, jsco)


    def validate(self, skip_schema=False):
        #-- only v0.6+
        if float(self.j["version"]) < 0.6:
            return (False, False, "Only files with version 0.6+ can be validated.", "")
        es = ""
        ws = ""
        #-- 1. schema
        if skip_schema == False:
            b, js = self.fetch_schema()
            if b == False:
                return (False, False, "Can't find the proper schema.", "")
            else:
                try:
                    validation.validate_against_schema(self.j, js)
                except Exception as e:
                    es += str(e)
                    return (False, False, es, "")
        #-- 2. ERRORS
        isValid = True
        b, errs = validation.city_object_groups(self.j) 
        if b == False:
            isValid = False
            es += errs
        b, errs = validation.building_parts(self.j) 
        if b == False:
            isValid = False
            es += errs
        b, errs = validation.building_installations(self.j)
        if b == False:
            isValid = False
            es += errs
        b, errs = validation.building_pi_parent(self.j)
        if b == False:
            isValid = False
            es += errs
        b, errs = validation.semantics(self.j)
        if b == False:
            isValid = False
            es += errs
        #-- 3. WARNINGS
        woWarnings = True
        b, errs = validation.metadata(self.j, js) 
        if b == False:
            woWarnings = False
            ws += errs
        b, errs = validation.cityjson_properties(self.j, js)
        if b == False:
            woWarnings = False
            ws += errs
        b, errs = validation.geometry_empty(self.j)
        if b == False:
            woWarnings = False
            ws += errs
        b, errs = validation.duplicate_vertices(self.j)
        if b == False:
            woWarnings = False
            ws += errs
        b, errs = validation.orphan_vertices(self.j)
        if b == False:
            woWarnings = False
            ws += errs
        #-- fetch schema cityobjects.json
        b, jsco = self.fetch_schema_cityobjects()
        b, errs = validation.citygml_attributes(self.j, jsco)
        if b == False:
            woWarnings = False
            ws += errs
        return (isValid, woWarnings, es, ws)

    def update_bbox(self):
        """
        Update the bbox (["metadata"]["bbox"]) of the CityJSON.
        If there is none then it is added.
        """
        if "metadata" not in self.j:
            self.j["metadata"] = {}
        if self.is_empty() == True:
            bbox = [0, 0, 0, 0, 0, 0]    
            self.j["metadata"]["bbox"] = bbox
            return bbox
        bbox = [9e9, 9e9, 9e9, -9e9, -9e9, -9e9]    
        for v in self.j["vertices"]:
            for i in range(3):
                if v[i] < bbox[i]:
                    bbox[i] = v[i]
            for i in range(3):
                if v[i] > bbox[i+3]:
                    bbox[i+3] = v[i]
        if "transform" in self.j:
            for i in range(3):
                bbox[i] = (bbox[i] * self.j["transform"]["scale"][i]) + self.j["transform"]["translate"][i]
            for i in range(3):
                bbox[i+3] = (bbox[i+3] * self.j["transform"]["scale"][i]) + self.j["transform"]["translate"][i]
        self.j["metadata"]["bbox"] = bbox
        return bbox        


    def set_crs(self, newcrs):
        if "metadata" not in self.j:
            self.j["metadata"] = {}
        if "crs" not in self.j["metadata"]:
            self.j["metadata"]["crs"] = {} 
        if "epsg" not in self.j["metadata"]["crs"]:
            self.j["metadata"]["crs"]["epsg"] = None
        try:
            i = int(newcrs)
            self.j["metadata"]["crs"]["epsg"] = i
            return True
        except ValueError:
            return False


    def get_crs(self):
        if "metadata" not in self.j:
            return None
        if "crs" not in self.j["metadata"]:
            return None
        if "epsg" not in self.j["metadata"]["crs"]:
            return None
        return self.j["metadata"]["crs"]["epsg"]


    def add_bbox_each_cityobjects(self):
        def recusionvisit(a, vs):
          for each in a:
            if isinstance(each, list):
                recusionvisit(each, vs)
            else:
                vs.append(each)
        for co in self.j["CityObjects"]:
            vs = []
            bbox = [9e9, 9e9, 9e9, -9e9, -9e9, -9e9]    
            for g in self.j['CityObjects'][co]['geometry']:
                recusionvisit(g["boundaries"], vs)
                for each in vs:
                    v = self.j["vertices"][each]
                    for i in range(3):
                        if v[i] < bbox[i]:
                            bbox[i] = v[i]
                    for i in range(3):
                        if v[i] > bbox[i+3]:
                            bbox[i+3] = v[i]
                if "transform" in self.j:
                    for i in range(3):
                        bbox[i] = (bbox[i] * self.j["transform"]["scale"][i]) + self.j["transform"]["translate"][i]
                    for i in range(3):
                        bbox[i+3] = (bbox[i+3] * self.j["transform"]["scale"][i]) + self.j["transform"]["translate"][i]
                self.j["CityObjects"][co]["bbox"] = bbox


    def get_centroid(self, coid):
        def recusionvisit(a, vs):
          for each in a:
            if isinstance(each, list):
                recusionvisit(each, vs)
            else:
                vs.append(each)
        #-- find the 3D centroid
        centroid = [0, 0, 0]
        total = 0
        for g in self.j['CityObjects'][coid]['geometry']:
            vs = []
            recusionvisit(g["boundaries"], vs)
            for each in vs:
                v = self.j["vertices"][each]
                total += 1
                centroid[0] += v[0]
                centroid[1] += v[1]
                centroid[2] += v[2]
        if (total != 0):
            centroid[0] /= total
            centroid[1] /= total
            centroid[2] /= total
            if "transform" in self.j:
                centroid[0] = (centroid[0] * self.j["transform"]["scale"][0]) + self.j["transform"]["translate"][0]
                centroid[1] = (centroid[1] * self.j["transform"]["scale"][1]) + self.j["transform"]["translate"][1]
                centroid[2] = (centroid[2] * self.j["transform"]["scale"][2]) + self.j["transform"]["translate"][2]
            return centroid
        else:
            return None


    def get_subset_bbox(self, bbox):
        # print ('get_subset_bbox')
        #-- new sliced CityJSON object
        cm2 = CityJSON()
        cm2.j["version"] = self.j["version"]
        if "transform" in self.j:
            cm2.j["transform"] = self.j["transform"]
        re = set()            
        for coid in self.j["CityObjects"]:
            centroid = self.get_centroid(coid)
            if ((centroid is not None) and
                (centroid[0] >= bbox[0]) and
                (centroid[1] >= bbox[1]) and
                (centroid[0] <  bbox[2]) and
                (centroid[1] <  bbox[3]) ):
                re.add(coid)
        #-- also add the parent of a Part/Installation
        re2 = copy.deepcopy(re)
        for theid in re2:
            for each in ['Parts', 'Installations', 'ConstructionElements']:
                if self.j["CityObjects"][theid]["type"].find(each[:-1]) > 0:
                    for coid in self.j["CityObjects"]:
                        if (each in self.j["CityObjects"][coid]) and (theid in self.j["CityObjects"][coid][each]):
                            re.add(coid)
        for each in re:
            cm2.j["CityObjects"][each] = self.j["CityObjects"][each]
        #-- geometry
        subset.process_geometry(self.j, cm2.j)
        #-- templates
        subset.process_templates(self.j, cm2.j)
        #-- appearance
        if ("appearance" in self.j):
            cm2.j["appearance"] = {}
            subset.process_appearance(self.j, cm2.j)
        #-- metadata
        if ("metadata" in self.j):
            cm2.j["metadata"] = self.j["metadata"]
        cm2.update_bbox()
        return cm2


    def get_subset_random(self, number=1):
        random.seed()
        total = len(self.j["CityObjects"])
        if number > total:
            number = total
        allkeys = list(self.j["CityObjects"].keys())
        lsIDs = []
        for each in range(number):
            lsIDs.append(allkeys[random.randint(0, total - 1)])
        return self.get_subset_ids(lsIDs)


    def get_subset_ids(self, lsIDs):
        #-- new sliced CityJSON object
        cm2 = CityJSON()
        cm2.j["version"] = self.j["version"]
        if "transform" in self.j:
            cm2.j["transform"] = self.j["transform"]
        #-- copy selected CO to the j2
        re = subset.select_co_ids(self.j, lsIDs)
        for each in re:
            cm2.j["CityObjects"][each] = self.j["CityObjects"][each]
        #-- geometry
        subset.process_geometry(self.j, cm2.j)
        #-- templates
        subset.process_templates(self.j, cm2.j)
        #-- appearance
        if ("appearance" in self.j):
            cm2.j["appearance"] = {}
            subset.process_appearance(self.j, cm2.j)
        #-- metadata
        if ("metadata" in self.j):
            cm2.j["metadata"] = self.j["metadata"]
        cm2.update_bbox()
        return cm2


    def get_subset_cotype(self, cotype):
        # print ('get_subset_cotype')
        lsCOtypes = [cotype]
        if cotype == 'Building':
            lsCOtypes.append('BuildingInstallation')
            lsCOtypes.append('BuildingPart')
        if cotype == 'Bridge':
            lsCOtypes.append('BridgePart')
            lsCOtypes.append('BridgeInstallation')
            lsCOtypes.append('BridgeConstructionElement')
        if cotype == 'Tunnel':
            lsCOtypes.append('TunnelInstallation')
            lsCOtypes.append('TunnelPart')
        #-- new sliced CityJSON object
        cm2 = CityJSON()
        cm2.j["version"] = self.j["version"]
        if "transform" in self.j:
            cm2.j["transform"] = self.j["transform"]
        #-- copy selected CO to the j2
        for theid in self.j["CityObjects"]:
            if self.j["CityObjects"][theid]["type"] in lsCOtypes:
                cm2.j["CityObjects"][theid] = self.j["CityObjects"][theid]
        #-- geometry
        subset.process_geometry(self.j, cm2.j)
        #-- templates
        subset.process_templates(self.j, cm2.j)
        #-- appearance
        if ("appearance" in self.j):
            cm2.j["appearance"] = {}
            subset.process_appearance(self.j, cm2.j)
        #-- metadata
        if ("metadata" in self.j):
            cm2.j["metadata"] = self.j["metadata"]
        cm2.update_bbox()
        return cm2
        


    def get_textures_location(self):
        """Get the location of the texture files
        
        Assumes that all textures are in the same location. Relative paths
        are expanded to absolute paths.
        """
        if "appearance" in self.j:
            if "textures" in self.j["appearance"]:
                p = self.j["appearance"]["textures"][0]["image"]
                cj_dir = os.path.dirname(self.path)
                url = re.match('http[s]?://|www\.', p)
                if url:
                    return url
                else:
                    d = os.path.dirname(p)
                    if len(d) == 0:
                        # textures are in the same dir as the cityjson file
                        return cj_dir
                    elif not os.path.isabs(d):
                        if os.path.isdir(os.path.abspath(d)):
                            # texture dir is not necessarily in the same dir 
                            # as the input file
                            return os.path.abspath(d)
                        elif os.path.isdir(os.path.join(cj_dir, d)):
                            # texture dir is a subdirectory at the input file
                            return os.path.join(cj_dir, d)
                        else:
                            raise FileNotFoundError("Texture directory '%s' not found" % d)
            else:
                print("This file does not have textures")
                return None
        else:
            print("This file does not have textures")
            return None

    def validate_textures(self):
        """Check if the texture files exist"""


    def remove_textures(self):
        for i in self.j["CityObjects"]:
            if "texture" in self.j["CityObjects"][i]:
                del self.j["CityObjects"][i]["texture"]
        if "appearance" in self.j:
            if "textures" in self.j["appearance"]:
                del self.j["appearance"]["textures"]
            if "vertices-texture" in self.j["appearance"]:
                del self.j["appearance"]["vertices-texture"]
            if "default-theme-texture" in self.j["appearance"]:
                del self.j["appearance"]["default-theme-texture"]
        # print (len(self.j["appearance"]))
        if self.j["appearance"] is None or len(self.j["appearance"]) == 0:
            del self.j["appearance"]
        return True


    def remove_materials(self):
        for i in self.j["CityObjects"]:
            if "material" in self.j["CityObjects"][i]:
                del self.j["CityObjects"][i]["material"]
        if "appearance" in self.j:
            if "materials" in self.j["appearance"]:
                del self.j["appearance"]["materials"]
            if "default-theme-material" in self.j["appearance"]:
                del self.j["appearance"]["default-theme-material"]
        if self.j["appearance"] is None or len(self.j["appearance"]) == 0:
            del self.j["appearance"]
        return True

    def get_info(self):
        info = collections.OrderedDict()
        info["cityjson_version"] = self.get_version()
        info["epsg"] = self.get_epsg()
        info["cityobjects_total"] = len(self.j["CityObjects"])
        d = set()
        for key in self.j["CityObjects"]:
            d.add(self.j['CityObjects'][key]['type'])
        info["cityobjects_present"] = list(d)
        info["vertices_total"] = len(self.j["vertices"])
        info["transform/compressed"] = "transform" in self.j
        d.clear()
        for key in self.j["CityObjects"]:
            for geom in self.j['CityObjects'][key]['geometry']:
                d.add(geom["type"])
        info["geom_primitives_present"] = list(d)
        if 'appearance' in self.j:
            info["materials"] = 'materials' in self.j['appearance']
            info["textures"] = 'textures' in self.j['appearance']
        else:
            info["materials"] = False
            info["textures"] =  False
        return json.dumps(info, indent=2)


    def remove_orphan_vertices(self):
        def visit_geom(a, oldnewids, newvertices):
          for i, each in enumerate(a):
            if isinstance(each, list):
                visit_geom(each, oldnewids, newvertices)
            else:
                if each not in oldnewids:
                    oldnewids[each] = len(newvertices)
                    newvertices.append(each)
        def update_face(a, oldnewids):
          for i, each in enumerate(a):
            if isinstance(each, list):
                update_face(each, oldnewids)
            else:
                a[i] = oldnewids[each]
        #--
        totalinput = len(self.j["vertices"])        
        oldnewids = {}
        newvertices = []
        #-- visit each geom to gather used ids 
        for theid in self.j["CityObjects"]:
                for g in self.j['CityObjects'][theid]['geometry']:
                    visit_geom(g["boundaries"], oldnewids, newvertices)
        #-- update the faces ids
        for theid in self.j["CityObjects"]:
                for g in self.j['CityObjects'][theid]['geometry']:
                    update_face(g["boundaries"], oldnewids)
        #-- replace the vertices, innit?
        newv2 = []
        for v in newvertices:
            newv2.append(self.j["vertices"][v])
        self.j["vertices"] = newv2
        return (totalinput - len(self.j["vertices"]))


    def remove_duplicate_vertices(self):
        def update_geom_indices(a, newids):
          for i, each in enumerate(a):
            if isinstance(each, list):
                update_geom_indices(each, newids)
            else:
                a[i] = newids[each]
        #--            
        totalinput = len(self.j["vertices"])        
        h = {}
        newids = [-1] * len(self.j["vertices"])
        newvertices = []
        for i, v in enumerate(self.j["vertices"]):
            s = str(v[0]) + " " + str(v[1]) + " " + str(v[2])
            if s not in h:
                newid = len(h)
                newids[i] = newid
                h[s] = newid
                newvertices.append(s)
            else:
                newids[i] = h[s]
        #-- update indices
        for theid in self.j["CityObjects"]:
                for g in self.j['CityObjects'][theid]['geometry']:
                    update_geom_indices(g["boundaries"], newids)
        #-- replace the vertices, innit?
        newv2 = []
        for v in newvertices:
            if "transform" in self.j:
                a = list(map(int, v.split()))
            else:
                a = list(map(float, v.split()))
            newv2.append(a)
        self.j["vertices"] = newv2
        return (totalinput - len(self.j["vertices"]))


    def compress(self, important_digits=3):
        if "transform" in self.j:
            raise Exception("CityJSON already compressed")
            return True
        #-- find the minx/miny/minz
        bbox = [9e9, 9e9, 9e9]    
        for v in self.j["vertices"]:
            for i in range(3):
                if v[i] < bbox[i]:
                    bbox[i] = v[i]
        #-- convert vertices in self.j to int
        n = [0, 0, 0]
        p = '%.' + str(important_digits) + 'f' 
        for v in self.j["vertices"]:
            for i in range(3):
                n[i] = v[i] - bbox[i]
            for i in range(3):
                v[i] = int((p % n[i]).replace('.', ''))
        #-- put transform
        self.j["transform"] = {}
        ss = '0.'
        ss += '0'*(important_digits - 1)
        ss += '1'
        ss = float(ss)
        self.j["transform"]["scale"] = [ss, ss, ss]
        self.j["transform"]["translate"] = [bbox[0], bbox[1], bbox[2]]
        #-- clean the file
        re = self.remove_duplicate_vertices()
        # print ("Remove duplicates:", re)
        re = self.remove_orphan_vertices()
        # print ("Remove orphans:", re)
        return True


    def decompress(self):
        if "transform" in self.j:
            for v in self.j["vertices"]:
                v[0] = (v[0] * self.j["transform"]["scale"][0]) + self.j["transform"]["translate"][0]
                v[1] = (v[1] * self.j["transform"]["scale"][1]) + self.j["transform"]["translate"][1]
                v[2] = (v[2] * self.j["transform"]["scale"][2]) + self.j["transform"]["translate"][2]
            del self.j["transform"]
            return True
        else: 
            return False


    def merge(self, lsCMs):
        # decompress() everything
        # updates CityObjects
        # updates vertices
        # updates geometry-templates
        # updates textures
        # updates materials
        #############################
        def update_geom_indices(a, offset):
          for i, each in enumerate(a):
            if isinstance(each, list):
                update_geom_indices(each, offset)
            else:
                if each is not None:
                    a[i] = each + offset
        def update_texture_indices(a, toffset, voffset):
          for i, each in enumerate(a):
            if isinstance(each, list):
                update_texture_indices(each, toffset, voffset)
            else:
                if each is not None:
                    if i == 0:
                        a[i] = each + toffset
                    else:
                        a[i] = each + voffset
        #-- decompress current CM                        
        self.decompress()
        for cm in lsCMs:
            #-- decompress 
            cm.decompress()
            #-- add each CityObjects
            coadded = 0
            for theid in cm.j["CityObjects"]:
                if theid in self.j["CityObjects"]:
                    print ("ERROR: CityObject #", theid, "already present. Skipped.")
                else:
                    self.j["CityObjects"][theid] = cm.j["CityObjects"][theid]
                    coadded += 1
            if coadded == 0:
                continue
            #-- add the vertices + update the geom indices
            offset = len(self.j["vertices"])
            self.j["vertices"] += cm.j["vertices"]
            for theid in cm.j["CityObjects"]:
                for g in cm.j['CityObjects'][theid]['geometry']:
                    update_geom_indices(g["boundaries"], offset)
            #-- templates
            if "geometry-templates" in cm.j:
                if "geometry-templates" in self.j:
                    notemplates = len(self.j["geometry-templates"]["templates"])
                    novtemplate = len(self.j["geometry-templates"]["vertices-templates"])
                else:
                    self.j["geometry-templates"] = {}
                    self.j["geometry-templates"]["templates"] = []
                    self.j["geometry-templates"]["vertices-templates"] = []
                    notemplates = 0
                    novtemplate = 0
                #-- copy templates
                for t in cm.j["geometry-templates"]["templates"]:
                    self.j["geometry-templates"]["templates"].append(t)
                    tmp = self.j["geometry-templates"]["templates"][-1]
                    update_geom_indices(tmp["boundaries"], novtemplate)
                #-- copy vertices
                self.j["geometry-templates"]["vertices-templates"] += cm.j["geometry-templates"]["vertices-templates"]
                #-- update the "template" in each GeometryInstance
                for theid in cm.j["CityObjects"]:
                    for g in self.j['CityObjects'][theid]['geometry']:
                        if g["type"] == 'GeometryInstance':
                            g["template"] += notemplates
            #-- materials
            if ("appearance" in cm.j) and ("materials" in cm.j["appearance"]):
                if ("appearance" in self.j) and ("materials" in self.j["appearance"]):
                    offset = len(self.j["appearance"]["materials"])
                else:
                    if "appearance" not in self.j:
                        self.j["appearance"] = {}
                    if "materials" not in self.j["appearance"]:
                        self.j["appearance"]["materials"] = {}
                    offset = 0
                #-- copy materials
                for m in cm.j["appearance"]["materials"]:
                    self.j["appearance"]["materials"].append(m)
                #-- update the "material" in each Geometry
                for theid in cm.j["CityObjects"]:
                    for g in self.j['CityObjects'][theid]['geometry']:
                        if 'material' in g:
                            for m in g['material']:
                                update_geom_indices(g['material'][m]['values'], offset)
            #-- textures
            if ("appearance" in cm.j) and ("textures" in cm.j["appearance"]):
                if ("appearance" in self.j) and ("textures" in self.j["appearance"]):
                    toffset = len(self.j["appearance"]["textures"])
                    voffset = len(self.j["appearance"]["vertices-texture"])
                else:
                    if "appearance" not in self.j:
                        self.j["appearance"] = {}
                    if "textures" not in self.j["appearance"]:
                        self.j["appearance"]["textures"] = {}
                    if "vertices-texture" not in self.j["appearance"]:
                        self.j["appearance"]["vertices-texture"] = {}                        
                    toffset = 0
                    voffset = 0
                #-- copy vertices-texture
                self.j["appearance"]["vertices-texture"] += cm.j["appearance"]["vertices-texture"]
                #-- copy textures
                for t in cm.j["appearance"]["textures"]:
                    self.j["appearance"]["textures"].append(t)
                #-- update the "texture" in each Geometry
                for theid in cm.j["CityObjects"]:
                    for g in self.j['CityObjects'][theid]['geometry']:
                        if 'texture' in g:
                            for m in g['texture']:
                                update_texture_indices(g['texture'][m]['values'], toffset, voffset)
        # self.remove_duplicate_vertices()
        # self.remove_orphan_vertices()
        return True



