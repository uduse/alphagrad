from typing import Callable, Sequence
from functools import partial

import jax
import jax.lax as lax
import jax.numpy as jnp
import jax.random as jrand
import jax.tree_util as jtu

from chex import PyTreeDef
import mctx
import equinox as eqx

from ..utils import symexp


# Preconfigured functions for tree search
select_params = lambda x, y: y if eqx.is_inexact_array(x) else x

def make_recurrent_fn(network: PyTreeDef,
                    step: Callable,
                    get_masked_logits: Callable) -> Callable:
    """TODO write docstring

    Args:
        nn_model (chex.PyTreeDef): _description_
        num_intermediates (int): _description_
        batched_step (Callable): _description_
        batched_get_masked_logits (Callable): _description_

    Returns:
        Callable: _description_
    """
    @partial(jax.vmap, in_axes=(None, None, 0, 0))
    def recurrent_fn(params, rng_key, actions, state):
        next_state, reward, _ = step(state, actions) # Env dynamics function
        
        # Map parameters to prediction function, i.e. neural network
        model = jtu.tree_map(select_params, network, params)

        # Compute policy and value for leaf node with neural network model
        # Symexp for reward scaling since value head is trained on symlog(value)
        output = model(next_state, rng_key)
        policy_logits = output[1:]
        value = symexp(output[0]) 
        
        # Create mask for invalid actions, i.e. already eliminated vertices
        masked_logits = get_masked_logits(policy_logits, state)

        # Expand the tree at the leaf with a new node
        # The initial action probabilities will be biased with the prediction
        # from the neural network
        # On a single-player environment, use discount from [0, 1].
        recurrent_fn_output = mctx.RecurrentFnOutput(reward=reward,
                                                    discount=1.,
                                                    prior_logits=masked_logits,
                                                    value=value)
        return recurrent_fn_output, next_state
    
    return recurrent_fn


def make_environment_interaction(num_considered_actions: int,
                                num_actions: int,
                                gumbel_scale: int,
                                num_simulations: int,
                                recurrent_fn: Callable,
                                step: Callable,
                                **kwargs) -> Callable:
    """
    TODO write docstring
    """
    qtransform = partial(mctx.qtransform_completed_by_mix_value, **kwargs)
    
    def environment_interaction(network, init_carry):
        batchsize = init_carry[1].shape[0]
        batched_network = eqx.filter_vmap(network)
        params = eqx.filter(network, eqx.is_inexact_array)
        
        def loop_fn(carry, _):
            state, rews, key = carry
            key, subkey = jrand.split(key, 2)
    
            # Create action mask
            mask = state.at[:, 1, 0, :].get()

            # Getting policy and value estimates
            # Symexp for reward scaling since value head is trained on symlog(value)
            keys = jrand.split(key, batchsize)
            output = batched_network(state, keys)
            policy_logits = output[:, 1:]
            values = symexp(output[:, 0]) 

            # Configuring root node of the tree search
            root = mctx.RootFnOutput(prior_logits=policy_logits, 
                                    value=values, 
                                    embedding=state)
                                    
            # Gumbel MuZero is so much better!
            # Smaller Gumbel noise helps improve performance, but too small kills learning
            policy_output = mctx.gumbel_muzero_policy(params,
                                                    subkey,
                                                    root,
                                                    recurrent_fn,
                                                    num_simulations,
                                                    invalid_actions=mask,
                                                    qtransform=qtransform,
                                                    gumbel_scale=gumbel_scale,
                                                    max_num_considered_actions=num_considered_actions)

            # Tree search derived targets for policy and value function
            search_policy = policy_output.action_weights
            
            # Always take action recommended by tree search
            action = policy_output.action

            # Step the environment
            next_state, rewards, done = jax.vmap(step)(state, action)
            rews += rewards	
            
            # Package up everything for further processing
            state_flattened = state.reshape(batchsize, -1)
            return (next_state, rews, key), jnp.concatenate([state_flattened,
                                                            search_policy, 
                                                            rews[:, jnp.newaxis], 
                                                            done[:, jnp.newaxis]], 
                                                            axis=1)

        _, output = lax.scan(loop_fn, init_carry, None, length=num_actions)
        return output.transpose(1, 0, 2)
    
    return environment_interaction
