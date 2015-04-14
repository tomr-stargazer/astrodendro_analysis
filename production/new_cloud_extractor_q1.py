"""
Extracts clouds from the first quadrant using the new cloud-first method.

"""

from __future__ import division

import numpy as np

import astropy
import astropy.units as u

from astrodendro_analysis.production.convenience_function import load_permute_dendro_catalog
from astrodendro_analysis.production.calculate_distance_dependent_properties import assign_properties
from astrodendro_analysis.production.remove_degenerate_structures import reduce_catalog
from astrodendro_analysis.production.detect_disparate_distances import detect_disparate_distances
from astrodendro_analysis.production.disqualify_edge_structures import identify_edge_structures

from astrodendro_analysis.reid_distance_assigner import make_reid_distance_column
from astrodendro_analysis.catalog_tree_stats import compute_tree_stats

from make_firstquad_stub import d, catalog, header, metadata


def first_quad_cloud_catalog():
    """
    This generates a 'processed' dendrogram catalog, made
    from the global, pre-loaded `catalog` from the first quadrant.

    It identifies edge structures, computes tree statistics,
    determines the near & far distances (but does not resolve them),
    assigns a distance when there is no KDA, and then assigns physical
    properties to the unambiguously-distanced structures.

    Its output is meant to be the input to `get_positive_velocity_clouds()`,
    `get_low_velocity_perseus_clouds()`, and
    `get_negative_velocity_clouds()`.

    """

    catalog_cp = catalog.copy(copy_data=True)

    # assignment of tree statistic properties
    compute_tree_stats(catalog_cp, d)

    # note edge structures
    catalog_cp['on_edge'] = identify_edge_structures(d)

    near_distance_table = make_reid_distance_column(catalog, nearfar='near')
    far_distance_table = make_reid_distance_column(catalog, nearfar='far')

    near_distance_column = near_distance_table['D_k']
    far_distance_column = far_distance_table['D_k']

    # DISTANCE assignment
    catalog_cp['near_distance'] = near_distance_column
    catalog_cp['far_distance'] = far_distance_column

    # where there's no degeneracy, go ahead and apply the thing
    no_degeneracy = catalog_cp['near_distance'] == catalog_cp['far_distance']
    distance_column = np.zeros_like(near_distance_column) * np.nan
    distance_column[no_degeneracy] = catalog_cp['near_distance'][no_degeneracy]

    catalog_cp['distance'] = distance_column

    # assignment of physical properties to unambigously-distanced structures
    # let's think critically about whether this step is needed.
    assign_properties(catalog_cp)

    return catalog_cp


def get_positive_velocity_clouds(input_catalog, max_descendants=30):
    """
    Extracts clouds from the positive-velocity region of the first quad.

    This is the 1Q's inner Galaxy.
    Here, the KDA applies to most structures, so we first define
    clouds based on (a) position in velocity space, (b) a cloud is not
    on an edge, (c) line widths between 1-10 km/s, (d) a cloud has less
    than `max_descendants` descendants, (e) the `fractional_gain` is
    below 0.81.

    Structures that meet the above criteria go into a pre-candidate-cloud
    list, and that list is "flattened" or "reduced" to remove degenerate
    substructure.

    Then the KDA is disambiguated for the relevant structures using the
    function `distance_disambiguator` and their physical properties are 
    computed.

    A final list of clouds is generated by taking structures with a mass
    greater than 3 x 10^4 solar masses; this is what's returned.

    """

    catalog = input_catalog.copy(copy_data=True)

    # one. grab the clouds we think are real
    disqualified = (
        (catalog['v_cen'] < 20) |
        (catalog['on_edge'] == 1) |
        (catalog['v_rms'] <= 1) |
        (catalog['v_rms'] > 10)
    )

    qualified = (
        (catalog['n_descendants'] < max_descendants) &
        (catalog['fractional_gain'] < 0.81))

    pre_output_catalog = catalog[~disqualified & qualified]

    # now it's just got clouds that COULD be real
    almost_output_catalog = reduce_catalog(d, pre_output_catalog)

    # disambiguate distances here
    best_distance = distance_disambiguator(almost_output_catalog)
    almost_output_catalog['distance'] = best_distance
    assign_properties(almost_output_catalog)

    # now let's do a thing
    final_qualified = (almost_output_catalog['mass'] > 3e4)
    output_catalog = almost_output_catalog[final_qualified]

    return output_catalog


def get_negative_velocity_clouds(input_catalog, max_descendants=30):
    """
    Extracts clouds from the negative-velocity region of the first quad.

    This is the 1Q's Outer Galaxy.
    Here, the KDA does not apply. We first define clouds based on 
    (a) position in velocity space, 
    (b) a cloud is not on an edge, 
    (c) a cloud has less than `max_descendants` descendants, 
    (d) the `fractional_gain` is below 0.81.

    Structures that meet the above criteria go into a pre-candidate-cloud
    list, and that list is "flattened" or "reduced" to remove degenerate
    substructure.

    Then the KDA is disambiguated for the relevant structures using the
    function `distance_disambiguator` and their physical properties are 
    computed.

    A final list of clouds is generated by taking structures with a mass
    greater than 3 x 10^3 solar masses; this is what's returned.

    Note that the mass criterion is an order of magnitude lower here 
    than in the positive-velocity region; this is mainly because
    (a) less confusion means these lower mass clouds are easy to 
        definitely identify, and
    (b) clouds here are overall lower-mass intrinsically, so we'd have a 
        low count if we didn't include them.

    """

    catalog = input_catalog.copy(copy_data=True)

    # narrow down how we select clouds
    disqualified = (
        (catalog['v_cen'] > -5) |
        # (catalog['mass'] < 10 ** 3.5 * u.solMass) |
        # (catalog['disparate'] == 0) |
        (catalog['on_edge'] == 1)
    )

    # qualified = (
    #     (catalog['n_descendants'] < max_descendants) &
    #     (catalog['fractional_gain'] < 0.81))

    # this step excludes the weird tail near the galactic center
    disqualified_extreme_negative_velocities_near_GC = (
        (catalog['v_cen'] < -10) & (catalog['x_cen'] < 20))

    pre_output_catalog = catalog[
        ~disqualified & ~disqualified_extreme_negative_velocities_near_GC]

    # now it's just got clouds that COULD be real
    almost_output_catalog = reduce_catalog(d, pre_output_catalog)

    # these objects already have mass, size etc computed so that's fine
    final_qualified = (almost_output_catalog['mass'] > 3e3)
    output_catalog = almost_output_catalog[final_qualified]

    return output_catalog


def get_low_velocity_perseus_clouds(input_catalog, max_descendants=30):
    """
    Extracts clouds from the low-velocity Perseus region of Q1.

    This is the 1Q's Perseus Arm at low velocities.
    Here, the KDA applies to some structures, and we are targeting clouds 
    that might overlap with local emission...
    so we first define clouds based on 
    (a) position in velocity space AND LATITUDE,
    (b) a cloud is not on an edge,
    (c) line widths between 1-10 km/s, 
    (d) a cloud has less than `max_descendants` descendants, 
    (e) the `fractional_gain` is below 0.81,

    Structures that meet the above criteria go into a pre-candidate-cloud
    list, and that list is "flattened" or "reduced" to remove degenerate
    substructure.

    Then the KDA is disambiguated for the relevant structures using the
    function `distance_disambiguator` and their physical properties are 
    computed.

    A final list of clouds is generated by taking structures with a mass
    greater than 3 x 10^4 solar masses AND a distance consistent with 
    the Perseus Arm; this is what's returned.

    """

    catalog = input_catalog.copy(copy_data=True)

    disqualified = (
        (catalog['v_cen'] < -5) |
        (catalog['v_cen'] > 20) |
        (np.abs(catalog['y_cen'] > 1)) |
        (catalog['x_cen'] < 35) |
        (catalog['on_edge'] == 1) |
        (catalog['v_rms'] <= 1) |
        (catalog['v_rms'] > 10)
    )

    qualified = (
        (catalog['n_descendants'] < max_descendants) &
        (catalog['fractional_gain'] < 0.81))

    pre_output_catalog = catalog[~disqualified & qualified]

    # now it's just got clouds that COULD be real
    almost_output_catalog = reduce_catalog(d, pre_output_catalog)

    # disambiguate distances here
    best_distance = distance_disambiguator(almost_output_catalog)
    almost_output_catalog['distance'] = best_distance
    assign_properties(almost_output_catalog)

    # now let's do a thing
    final_qualified = (
        (almost_output_catalog['mass'] > 3e4) &
        (almost_output_catalog['distance'] > 5) &
        (almost_output_catalog['distance'] < 14)
        )

    output_catalog = almost_output_catalog[final_qualified]

    return output_catalog


def distance_disambiguator(catalog):
    """
    Chooses the best distance based on size-linewidth fit & latitude.

    Currently, it's really crude about the latitude part.

    """

    near_distance_column = catalog['near_distance']
    far_distance_column = catalog['far_distance']

    best_distance = np.zeros_like(near_distance_column)

    sky_radius = u.Quantity(catalog['radius'].data * catalog['radius'].unit)
    near_distance = u.Quantity(near_distance_column)
    near_size = sky_radius.to(u.rad).value * near_distance

    far_distance = u.Quantity(far_distance_column)
    far_size = sky_radius.to(u.rad).value * far_distance

    quad2_fit_constant = 0.48293812090592952
    quad2_fit_power = 0.56796770148326814

    expected_size = (
        1 / quad2_fit_constant * catalog['v_rms'].data) ** (1 / quad2_fit_power) * u.pc

    use_near_distance = (np.abs(near_size - expected_size) <= np.abs(far_size - expected_size))
    use_far_distance = (np.abs(near_size - expected_size) > np.abs(far_size - expected_size))

    use_near_distance_latitude = (np.abs(catalog['y_cen']) > 1)

    best_distance[use_near_distance] = near_distance[use_near_distance]
    best_distance[use_far_distance] = far_distance[use_far_distance]

    # an override based on latitude
    best_distance[use_near_distance_latitude] = near_distance[use_near_distance_latitude]

    return best_distance


def compile_firstquad_catalog(input_catalog):

    negative_v_catalog = get_negative_velocity_clouds(input_catalog)
    positive_v_catalog = get_positive_velocity_clouds(input_catalog)
    low_v_catalog = get_low_velocity_perseus_clouds(input_catalog, max_descendants=10)

    composite_unreduced_catalog = astropy.table.vstack([negative_v_catalog, positive_v_catalog, low_v_catalog])

    composite_reduced_catalog = reduce_catalog(d, composite_unreduced_catalog)

    return composite_reduced_catalog

