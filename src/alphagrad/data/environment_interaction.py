from typing import Callable
import functools as ft

import jax
import jax.nn as jnn
import jax.lax as lax
import jax.numpy as jnp
import jax.random as jrand
import jax.tree_util as jtu

import chex
import mctx
import equinox as eqx

from graphax import GraphInfo

# TODO needs adjustment to new auto-regressive models!
# TODO add documentation
def make_recurrent_fn(nn_model: chex.PyTreeDef,
                    info: GraphInfo, 
                    batched_step: Callable,
                    batched_get_masked_logits: Callable) -> Callable:
    """TODO write docstring

    Args:
        nn_model (chex.PyTreeDef): _description_
        num_intermediates (int): _description_
        batched_step (Callable): _description_
        batched_get_masked_logits (Callable): _description_

    Returns:
        Callable: _description_
    """
    def recurrent_fn(params, rng_key, actions, state) -> Callable:
        batchsize, nn_params = params
        next_state, reward, _ = batched_step(state, actions) # dynamics function
        next_obs = next_state.edges

        # prediction function
        network = jtu.tree_map(lambda x, y: y if eqx.is_inexact_array(x) else x, nn_model, nn_params)
        batch_network = jax.vmap(network)

        keys = jrand.split(rng_key, batchsize)
        output = batch_network(next_obs, keys)
        policy_logits = output[:, 1:]
        value = output[:, 0]
        masked_logits = batched_get_masked_logits(policy_logits, 
                                                state, 
                                                info.num_intermediates)

        # On a single-player environment, use discount from [0, 1].
        discount = jnp.ones(batchsize)
        recurrent_fn_output = mctx.RecurrentFnOutput(reward=reward,
                                                    discount=discount,
                                                    prior_logits=masked_logits,
                                                    value=value)
        return recurrent_fn_output, next_state
    
    return recurrent_fn


def make_environment_interaction(info: GraphInfo,
                                num_simulations: int,
                                recurrent_fn: Callable,
                                batched_step: Callable,
                                batched_one_hot: Callable, 
                                **kwargs) -> Callable:
    """
    TODO write docstring
    """
    @ft.partial(eqx.filter_pmap, in_axes=(None, 0), backend="cpu")
    def environment_interaction(network, init_carry):
        batchsize = init_carry[1].shape[0]
        batched_network = eqx.filter_vmap(network)
        nn_params = eqx.filter(network, eqx.is_inexact_array)
        
        def loop_fn(carry, _):
            state, rews, key = carry
            obs = state.edges
    
            # create action mask
            one_hot_state = batched_one_hot(state.vertices-1, info.num_intermediates)
            mask = one_hot_state.sum(axis=1)

            keys = jrand.split(key, batchsize)
            output = batched_network(obs, keys)
            policy_logits = output[:, 1:]
            values = output[:, 0]

            root = mctx.RootFnOutput(prior_logits=policy_logits,
                                    value=values,
                                    embedding=state)

            key, subkey = jrand.split(key, 2)

            params = (batchsize, nn_params)
            qtransform = ft.partial(mctx.qtransform_completed_by_mix_value,
                                    use_mixed_value=True)
            policy_output = mctx.muzero_policy(params,
                                                subkey,
                                                root,
                                                recurrent_fn,
                                                num_simulations,
                                                invalid_actions=mask,
                                                qtransform=qtransform,
                                                **kwargs)

            # tree search derived targets for policy and value function
            search_policy = policy_output.action_weights

            # always take action recommended by tree search
            action = policy_output.action

            # step the environment
            next_state, rewards, done = batched_step(state, action)
            rews += rewards	
            obs_flattened = obs.reshape(batchsize, -1)
            return (next_state, rews, key), jnp.concatenate([obs_flattened,
                                                            search_policy, 
                                                            rews[:, jnp.newaxis], 
                                                            done[:, jnp.newaxis]], 
                                                            axis=1)

        _, output = lax.scan(loop_fn, init_carry, None, length=info.num_intermediates)
        return jnp.stack(output).transpose(1, 0, 2)
    
    return environment_interaction

