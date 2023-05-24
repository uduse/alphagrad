from typing import Sequence

import jax
import jax.numpy as jnp

from graphax import VertexGameState
from alphagrad.utils import preprocess_data


# TODO documentation
def batch_vertex_game_states(games: Sequence[VertexGameState]) -> VertexGameState:
	batchsize = len(games)
	ts = jnp.zeros(batchsize)
	infos = jnp.stack([jnp.array(game.info) for game in games])
	edges = jnp.stack([game.edges for game in games])
	vertices = jnp.zeros((batchsize, games[0].info.num_intermediates))
	return VertexGameState(t=ts,
							info=infos,
							edges=edges,
							vertices=vertices)


# TODO documentation
def differentiate(network, env_interaction_fn, key, *games):
	batch_games = batch_vertex_game_states(games)
	init_carry = preprocess_data(batch_games, key)
	output = env_interaction_fn(network, init_carry)
	return output[:, -1, -2].flatten()
