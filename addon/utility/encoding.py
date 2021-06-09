
import json
from . import distributors
from .. property import kitops_synth
from kitops.addon.utility import addon as kitops_addon
import uuid


def as_recipe(dct):
     if '__recipe__' in dct:
         return complex(dct['real'], dct['imag'])
     return dct

def _encode_inserts(inserts):
    """Encode a set of INSERTs"""
    encoded_inserts = []
    for insert in inserts:
        encoded_inserts.append( { 
                                    'is_enabled'            : insert.is_enabled,
                                    'category'              : insert.category,
                                    'insert_name'           : insert.insert_name,
                                    'proportionality'       : insert.proportionality,
                                    'scale'                 : insert.scale,
                                    'maintain_aspect_ratio' : insert.maintain_aspect_ratio,
                                    'use_once'              : insert.use_once,
                                    'do_not_scale'          : insert.do_not_scale
                                })

    return encoded_inserts

def _encode_distribution(layer):
    distribution_class_name = layer.distribution
    distributor = getattr(distributors, distribution_class_name)()
    return {
        'type' : layer.distribution,
        'parameters' : distributor.encode(layer)
    }


class RecipeEncoder(json.JSONEncoder):
    """Encodes a KIT OPS SYNTH Recipe"""
    def default(self, obj):
        if isinstance(obj, kitops_synth):
            kitopssynth = obj
            layers_to_encode = [{
                                    'layer_name' : layer.layer_name,
                                    'is_enabled' : layer.is_enabled,
                                    'seed'       : layer.seed,
                                    'frequency' : layer.frequency,
                                    'padding'   : layer.padding,
                                    'scale_x_deviation' : layer.scale_x_deviation,
                                    'scale_y_deviation' : layer.scale_y_deviation,
                                    'scale_z_deviation' : layer.scale_z_deviation,
                                    'z_position' : layer.z_position,
                                    'rotation'  : layer.rotation,
                                    'rotation_respect_borders' : layer.rotation_respect_borders,
                                    'rotation_deviation' : layer.rotation_deviation,
                                    'inserts' : _encode_inserts(layer.inserts),
                                    'distribution' : _encode_distribution(layer),
                                    'boolean_solver' : layer.boolean_solver,

                                } for layer in kitopssynth.layers]
            return {
                'description' : kitopssynth.description,
                'seed' : kitopssynth.seed,
                'layers' : layers_to_encode
            }
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)

def _decode_distribution(distributionJSON, layer):
    distribution_class_name = distributionJSON['type']
    layer.distribution = distribution_class_name
    distributor = getattr(distributors, distribution_class_name)()
    distributor.decode(distributionJSON['parameters'], layer)

def _decode_inserts(insertsJSON, layer):
    layer.inserts.clear()
    for insertJSON in insertsJSON:
        insert = layer.inserts.add()
        insert.is_enabled               = insertJSON['is_enabled']
        insert.is_expanded              = insert.is_enabled
        try:
            option = kitops_addon.option()
            found = False
            if ('category' in insertJSON and insertJSON['category']) and \
                ('insert_name' in insertJSON and insertJSON['insert_name']):
                category_name                 = insertJSON['category']
                insert_name                   = insertJSON['insert_name']
                for category in option.kpack.categories:
                    if category.name == category_name and insert_name in category.blends:
                        insert.category                 = category_name
                        insert.insert_name              = insert_name
                        found = True
                        break
            if not found and len(option.kpack.categories) and len(option.kpack.categories[0].blends):
                # if we didn't find anything, just set to the first category and insert entry.
                insert.category = option.kpack.categories[0].name
                insert.insert_name = option.kpack.categories[0].blends[0].name
                # if the insert is enabled, we'll assume it was expected so propogate the error message
                if insert.is_enabled:
                    raise TypeError()

        except TypeError:
            insert.error_message = "Error loading category: \'" + insertJSON['category'] + "\' with insert \'" + insertJSON['insert_name'] + "\'"

        insert.proportionality          = insertJSON['proportionality']
        insert.scale                    = insertJSON['scale']
        insert.maintain_aspect_ratio    = insertJSON['maintain_aspect_ratio']
        insert.use_once                 = insertJSON['use_once'] if 'use_once' in insertJSON else False
        insert.do_not_scale             = insertJSON['do_not_scale'] if 'do_not_scale' in insertJSON else False

def decode_recipe(recipeJSON, context):
    kitopssynth = context.scene.kitopssynth
    kitopssynth.description = recipeJSON['description'] if 'description' in recipeJSON else ''
    kitopssynth.seed = recipeJSON['seed'] if 'seed' in recipeJSON else 0
    kitopssynth.layers.clear()
    for layerJSON in recipeJSON['layers']:
        layer                           = kitopssynth.layers.add()
        layer.name                      = str(uuid.uuid4())
        layer.layer_name                = layerJSON['layer_name']
        layer.is_enabled                = layerJSON['is_enabled']
        layer.seed                      = layerJSON['seed']
        layer.frequency                 = layerJSON['frequency']
        layer.padding                   = layerJSON['padding']
        layer.scale_x_deviation         = layerJSON['scale_x_deviation']
        layer.scale_y_deviation         = layerJSON['scale_y_deviation']
        layer.scale_z_deviation         = layerJSON['scale_z_deviation']
        layer.z_position                = layerJSON['z_position']
        layer.rotation                  = layerJSON['rotation']
        layer.rotation_respect_borders  = layerJSON['rotation_respect_borders'] if 'rotation_respect_borders' in layerJSON else False
        layer.rotation_deviation        = layerJSON['rotation_deviation']
        layer.boolean_solver            = layerJSON['boolean_solver']
        _decode_inserts(layerJSON['inserts'], layer)
        _decode_distribution(layerJSON['distribution'], layer)



    

