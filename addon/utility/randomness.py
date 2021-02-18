# Helper class for geometric and other calculations.
import numpy as np
from mathutils import Vector
from .. utility import addon

_max_seed = 2**32 - 1
def random_generator(context, layer):
    """Get a randon number generator from a user provided seed."""
    preference = context.scene.kitopssynth

    if layer.seed == 0:
        seed_concatenated = int(str(preference.seed) + str(layer.index)) 
        rng = np.random.RandomState(seed_concatenated % _max_seed)
    else:
        rng = np.random.RandomState((preference.seed + layer.seed) % _max_seed)
    return rng

#TODO redundant for now.
def point_on_triangle(pt1, pt2, pt3, rng):
    """Calculate random point on the triangle with vertices pt1, pt2 and pt3."""
    s, t, = sorted([rng.uniform(0,1), rng.uniform(0,1)])
    return Vector((s * pt1[0] + (t-s)*pt2[0] + (1-t)*pt3[0],
            s * pt1[1] + (t-s)*pt2[1] + (1-t)*pt3[1],
            s * pt1[2] + (t-s)*pt2[2] + (1-t)*pt3[2]))