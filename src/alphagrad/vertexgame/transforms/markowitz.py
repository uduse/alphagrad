from functools import partial
from typing import Sequence

import jax
import jax.lax as lax
import jax.numpy as jnp

from chex import Array

from ..core import vertex_eliminate, get_shape


def safe_preeliminations(edges: Array, return_order: bool = False):
    """
    Eliminates only vertices with minimal Markowitz degree 0 and 1.
    """
    num_i, num_vo = get_shape(edges)
    
    def loop_fn(_edges, _):
        degree, mMd_vertex = get_minimal_markowitz(_edges)
        _edges, vertex = lax.cond(degree < 2,
                                lambda e: (vertex_eliminate(mMd_vertex, e)[0], mMd_vertex),
                                lambda e: (e, -1), 
                                _edges)
        return _edges, vertex
    
    it = jnp.arange(1, num_vo+1)
    edges, preelim_order = lax.scan(loop_fn, edges, it)
    
    if return_order:
        return edges, [int(p) for p in preelim_order if p > 0]
    return edges

@partial(jax.jit, static_argnums=1)
def minimal_markowitz(edges: Array, num_v: int) -> Sequence[int]:    
    def loop_fn(_edges, _):
        degree, mMd_vertex = get_minimal_markowitz(_edges)
        _edges, _ = vertex_eliminate(mMd_vertex, _edges)
        return _edges, mMd_vertex

    it = jnp.arange(1, num_v+1)
    _, idxs = lax.scan(loop_fn, edges, it)

    # TODO make this jittable, 
    # removed if edges.at[2, 0, i-1].get() == 0 else -1
    return [i.astype(jnp.int32) for i in idxs]


def get_minimal_markowitz(edges: Array, degrees: bool = False) -> Sequence[int]:
    """
    Function that calculates the elimination order of a computational graph
    with regard to the minimal Markowitz degree.
    To do this it calculates the markowitz degree of a single vertex within a
    group of similar vertices, i.e. for a single component of a tensor vertex.
    """    
    def loop_fn(carry, vertex):
        is_eliminated_vertex = edges.at[1, 0, vertex-1].get() == 1
        markowitz_degree = lax.cond(is_eliminated_vertex,
                                    lambda v, e: -1, 
                                    lambda v, e: calc_markowitz_degree(v, e), 
                                    vertex, edges)
        return carry, markowitz_degree
    
    vertices = jnp.arange(1, edges.shape[-1]+1)
    _, markowitz_degrees = lax.scan(loop_fn, (), vertices)
    if degrees:
        print(markowitz_degrees)
    idx = jnp.sum(edges.at[1, 0, :].get())
    mMd_vertex = jnp.argsort(markowitz_degrees)[idx]+1
    return markowitz_degrees[mMd_vertex-1], mMd_vertex


def calc_markowitz_degree(vertex: int, edges: Array):
    num_i, num_vo = get_shape(edges)
    in_edge_slice = edges.at[:, vertex+num_i, :].get()
    out_edge_slice = edges.at[:, 1:, vertex-1].get()      

    in_edge_count = count_in_edges(in_edge_slice)
    out_edge_count = count_out_edges(out_edge_slice)
    return in_edge_count * out_edge_count


def count_in_edges(edge_slice: Array):
    def loop_fn(num_edges, slice):
        sparsity_type = slice.at[0].get()
        _num_edges = lax.cond(sparsity_type == 1,
                            lambda s: jnp.prod(s.at[3:].get()),
                            lambda s: matrix_parallel(s),
                            slice)
        num_edges += _num_edges
        return num_edges, None

    num_edges, _ = lax.scan(loop_fn, 0, edge_slice.T)
    
    return num_edges


def count_out_edges(edge_slice: Array):
    def loop_fn(num_edges, slice):
        sparsity_type = slice.at[0].get()
        _num_edges = lax.cond(sparsity_type == 1,
                            lambda s: jnp.prod(s.at[1:3].get()),
                            lambda s: matrix_parallel(s),
                            slice)
        num_edges += _num_edges
        return num_edges, None

    num_edges, _ = lax.scan(loop_fn, 0, edge_slice.T)
    
    return num_edges


def matrix_parallel(slice: Array):
    sparsity_type = slice.at[0].get()
    mp = jnp.logical_or(sparsity_type == 6, sparsity_type == 7)
    _num_edges = lax.cond(jnp.logical_or(mp, sparsity_type == 8),
                        lambda s: 1,
                        lambda s: vector_parallel(s),
                        slice)
    return _num_edges


SPARSITY_MAP = jnp.array([2, 1, 1, 2])

def vector_parallel(slice: Array):
    sparsity_type = slice.at[0].get()
    idxs = SPARSITY_MAP[sparsity_type-2]
    return slice.at[idxs].get()

