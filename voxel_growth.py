# encoding: utf-8

##################################################
# Software 1 Group 04
##################################################
#
##################################################
# Author: Matt Gordon / Jun Lee / Amit Pattar
# Copyright: Copyright 2019, IAAC
# Credits: [Institute for Advanced Architecture of Catalonia - IAAC, MRAC group]
# License:  Apache License Version 2.0
# Version: 1.0.0
# Maintainer: Matt Gordon
# Email: matthew.gordon@students.iaac.net
# Status: development
##################################################

import math
import random

import rhinoscriptsyntax as rs
import ghpythonlib.components as gh

# === GLOBAL VARIABLES ===

# World Geometry
world_xy = gh.XYPlane(gh.ConstructPoint(0,0,0))
world_xz = gh.XZPlane(gh.ConstructPoint(0,0,0))
world_yz = gh.YZPlane(gh.ConstructPoint(0,0,0))

world_planes = [world_xy , world_xz, world_yz]

# World Sizes
slice_size = grid_size * grid_size
vlength = slice_size * grid_size

max_dist = 6928

# Deltas in Voxel Space: (+z, +y, +x, -y, -x, -z)  
dxv = (0,0,1,0,-1,0)
dyv = (0,1,0,-1,0,0)
dzv = (1,0,0,0,0,-1)

# Gen variables
max_cells =  2000
cell_count = 0

factor_attractor = 0.9

factor_void = 1
factor_perlin = 0.8
score_crowding = 50

growth_per_cell = 2

use_points = True
use_volumes = True
use_crowding = False
use_first = False
use_age = True
use_perlin = True


live_cells = []
attempts = []
attempt_scores = []

""" Iteration in which a cell was activated """
cell_age = [] 

# Precomputed Score Values
volume_void_inclusion = []
attract_point_distances = []


# === DEFINITIONS ===
def loc_to_cart(loc):
    """ Converts a 1d cell to a 3d cell"""
    return (loc % grid_size, loc % slice_size // grid_size, loc // slice_size)
    
def cart_to_loc(cart):
    """ Converts a 3d cell to a 1d cell"""
    return (cart[2] * slice_size) + (cart[1] * grid_size) + cart[0]
    
def get_cart_neighbor(cart,id):
    """ Returns a 3d cell given a direction from an existing 3d cell"""
    return (cart[0] + dxv[id],cart[1] + dyv[id],cart[2] + dzv[id])
    
def check_cart(cart):
    """ Returns True if the cell is within the voxel domain"""
    return 0 <= cart[0] < grid_size and 0 <= cart[1] < grid_size and 0 <= cart[2] < grid_size
   
def get_neighbor_live_count(cart):
    """ Returns the number of live neighbors surrounding a 3d cell"""
    count = 0
    for i in range(6):
        cart2 = (cart[0] + dxv[i],cart[1] + dyv[i],cart[2] + dzv[i])
        if check_cart(cart2) and voxel_data[cart_to_loc(cart2)] == 1:
            count += 1
    return count
    
def lerp(val,s1,e1,s2,e2):
    range1 = e1 - s1
    range2 = e2 - s2
    
    normal = (val - s1) / range1
    
    return (normal * range2) + s2
    
def clamp(val,min_val,max_val):
    return(max(min(val, max_val), min_val))

def check_dead(cart):
    """ Returns True if the cell is not alive"""
    id = cart_to_loc(cart)
    return voxel_data[id] == 0
    
def precompute_scoring():
    """ Run gh volume inclusion and attractor distance calculations for every voxel point in the domain"""
    global volume_void_inclusion
    global attract_point_distances
    global perlin_values
    
    volume_void_inclusion = []
    for i,void in enumerate(volumes_void):
        inclusion = gh.PointInBrep(void,points_input,False)
        volume_void_inclusion.append(inclusion)
        
    attract_point_distances = []
    for i,point in enumerate(points_attractor):
        distances = gh.Division(gh.Distance(point,points_input),max_dist)
        attract_point_distances.append(distances)
    

def strategy_attractors(cart):
    global attempts
    global attempt_scores

    del attempts[:]
    del attempt_scores[:]
    
    neighbors = [get_cart_neighbor(cart,i) for i in range(6)]
    neighbors = [c for c in neighbors if check_cart(c)]
    scores = [get_cart_score(c) for c in neighbors]
    
    neighbors = [x for _,x in sorted(zip(scores,neighbors))]
    neighbors.reverse()
    scores = sorted(scores)
    scores.reverse()
    
    attempts = attempts + neighbors
    attempt_scores = attempt_scores + scores
    
def get_cart_score(cart):
    global factor_attractor
    global factor_void
    global score_volume
    global factor_perlin
    
    loc = cart_to_loc(cart)
    score = 0
    
    fa_local = factor_attractor
    
    if use_age:
        fa_local *= (1- (1.00 * cell_count / max_cells))
    if use_points:
        for i,pa in enumerate(points_attractor):
            d = attract_point_distances[i][loc]
            score += (1 - d) * fa_local
    if use_volumes:
        for i,vv in enumerate(volumes_void):
            if volume_void_inclusion[i][loc]:
                score -= factor_void
    if use_crowding:
        neighbor_count = get_neighbor_live_count(cart)
        score -= (score_crowding * neighbor_count)
    if use_perlin:
        score += perlin_values[cart_to_loc(cart)] * factor_perlin
    # if use_age:
        # age_score = 0
        # neighbors = [get_cart_neighbor(cart,i) for i in range(6)]
        # for n in neighbors:
            # if check_cart(n) and not check_dead(n):
                # age_score += cell_age[cart_to_loc(n)]
        # age_score /= 100.0
        # score -= age_score
    
    return score
    
def mesh_strategy_neighbors(cart):
    neighbors = get_neighbor_live_count(cart)
    id = 0
    if neighbors <= 2:
        id = 0
    elif neighbors <= 4:
        id = 1
    else:
        id = 2
    return id
    
def mesh_strategy_vertical(cart):
    id = 1
    
    cart_up = get_cart_neighbor(cart,0)
    cart_down = get_cart_neighbor(cart,5)
    
    up_good = check_cart(cart_up) and not check_dead(cart_up)
    down_good = check_cart(cart_down) and not check_dead(cart_down)
    
    if up_good == down_good:
        id = 1
    elif up_good:
        id = 0
    elif down_good:
        id = 2
    
    return id

def copy_modules():
    global meshes_a,meshes_b,meshes_c
    # Copying Modules
    meshes_a = []
    meshes_b = []
    meshes_c = []
    totals = [0,0,0]
    for i,p in enumerate(points_input):
        d = voxel_data[i]
        if d == 0:
            continue
        cart = loc_to_cart(i)

        mesh_id = mesh_strategy_neighbors(cart)
        
        translation = gh.Vector2Pt(world_xy,p,False)[0]
        
        add = clamp(int((gh.Deconstruct(p)[2] / 4000 * 4) + (perlin_values[i] - 0.5)),0,3)
        
        
        if mesh_id == 0:
            meshes_a.append(gh.Move(mesh_input[16 + add],translation)[0])
        elif mesh_id == 1:
            meshes_a.append(gh.Move(mesh_input[12 + add],translation)[0])
            meshes_b.append(gh.Move(mesh_input[8 + add],translation)[0])
        elif mesh_id == 2:
            meshes_b.append(gh.Move(mesh_input[4 + add],translation)[0])
            meshes_c.append(gh.Move(mesh_input[0 + add],translation)[0])
            
        
        totals[mesh_id] += 1
        
        
        
        #new_plane = gh.PlaneOrigin(random.choose
        
        
        
    print totals

def run_pass():
    global live_cells
    global cell_count
    global attempts
    
    live_cells_next = []
    for i,cell in enumerate(live_cells):
        if cell_count >= max_cells:
            break
        if use_first:
            id = 0
        else:
            id = random.randint(0,len(live_cells) - 1)

        voxel_data[cart_to_loc(cell)] = 1
            
        strategy_attractors(cell)

        cells_added = 0
        for i,n in enumerate(attempts):
            if check_cart(n) and check_dead(n) and not n in live_cells_next:
                if cells_added == 0:
                    live_cells_next.insert(0,n)
                else:
                    live_cells_next.append(n)
                    
                cells_added += 1
                cell_count += 1
                
                attempt_loc = cart_to_loc(n)
                
                if perlin_values[attempt_loc] > perlin_cutoff:
                    break

                
                if cells_added == growth_per_cell:
                    break
                    
    del live_cells[:]
    live_cells = live_cells + live_cells_next

def run_pass_2():
    """ Every cell is live, combine cell and neighbor choosing"""
    global live_cells
    global cell_count
    global attempts
    global cell_age
    
    print("Live Cells : " + str(len(live_cells)))
    
    live_cell_scores = [get_cart_score(c) for c in live_cells]
    live_cells_sorted = [x for _,x in sorted(zip(live_cell_scores,live_cells))]
    del live_cells[:]
    live_cells = live_cells + live_cells_sorted
    
    cell = live_cells.pop(0)
    if check_cart(c) and check_dead(c):
        voxel_data[cart_to_loc(cell)] = 1
        
        cell_age[cart_to_loc(c)] = cell_count
        
        
        cell_count += 1
            
        neighbors = [get_cart_neighbor(c,i) for i in range(6)]
            
        for n in neighbors:
            if check_cart(n) and check_dead(c) and not n in live_cells:
                live_cells.append(n)

    
def main():
    global mesh_result
    global live_cells
    global attempts
    global cell_age

    # Initialize random seed

    precompute_scoring()


    cell_age = [0] * len(points_input)

    # Initial Seed Cells
    live_cells = []
    
    for sp in seed_points:
        cart = [ int(n / voxel_size) for n in gh.Deconstruct(sp)]
        live_cells.append(cart)

    while len(live_cells) > 0 and cell_count <= max_cells:
        run_pass()
            
    print("Live Cells Left : " + str(len(live_cells)))
    print("Cell Count : " + str(cell_count))
        
    copy_modules()

    


main()