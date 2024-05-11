"""
Implementation of PPO with insights from https://iclr-blog-track.github.io/2022/03/25/ppo-implementation-details/
"""

import os
import argparse
from functools import partial, reduce

import jax
import jax.nn as jnn
import jax.lax as lax
import jax.numpy as jnp
import jax.random as jrand

import numpy as np

from tqdm import tqdm
import wandb

import distrax
import optax
import equinox as eqx

from alphagrad.config import setup_experiment
from alphagrad.experiments import make_benchmark_scores
from alphagrad.vertexgame import step
from alphagrad.utils import symlog, symexp, entropy, explained_variance
from alphagrad.transformer.models import PolicyNet, ValueNet


# 324 RoeFlux_1d
# [68, 16, 24, 76, 63, 32, 70, 61, 80, 38, 52, 99, 43, 30, 83, 34, 74, 86, 62, 
# 8, 67, 4, 37, 50, 3, 44, 33, 15, 7, 42, 26, 28, 41, 10, 97, 21, 13, 88, 59, 
# 47, 49, 84, 95, 64, 36, 72, 27, 93, 25, 94, 78, 75, 90, 89, 81, 0, 20, 65, 77, 
# 31, 66, 46, 14, 12, 18, 71, 9, 87, 6, 45, 85, 91, 79, 57, 53, 17, 73, 51, 69, 
# 5, 54, 60, 92, 56, 58, 1, 39, 55, 82, 40, 2, 48, 22, 19, 35, 23, 11, 29]

# 247 RobotArm_6DOF
# [5, 94, 9, 20, 8, 13, 96, 66, 6, 93, 76, 104, 103, 95, 102, 21, 106, 17, 18, 
# 81, 112, 77, 78, 63, 64, 52, 79, 98, 51, 62, 111, 69, 37, 89, 19, 22, 26, 4, 
# 110, 39, 1, 100, 25, 54, 80, 107, 34, 53, 90, 105, 70, 74, 36, 43, 28, 42, 45, 
# 44, 38, 40, 75, 29, 68, 55, 60, 10, 87, 86, 7, 32, 48, 72, 109, 83, 50, 35, 
# 85, 59, 99, 24, 97, 73, 33, 49, 57, 58, 31, 16, 108, 30, 41, 82, 92, 27, 91, 
# 47, 46, 0, 12, 56, 71, 14, 88, 15, 2, 3, 23, 11]

# 247 RobotArm_6DOF
# [5, 76, 79, 6, 21, 81, 52, 104, 103, 95, 64, 112, 106, 102, 18, 63, 78, 68, 7, 
# 17, 71, 100, 98, 73, 39, 34, 93, 77, 8, 20, 31, 85, 111, 13, 62, 53, 40, 49, 
# 94, 9, 66, 51, 46, 19, 25, 107, 54, 90, 99, 59, 4, 10, 44, 86, 109, 60, 57, 
# 32, 70, 83, 108, 80, 89, 96, 22, 48, 24, 37, 26, 105, 97, 36, 1, 87, 56, 50, 
# 35, 45, 16, 30, 28, 29, 92, 110, 43, 33, 91, 75, 74, 58, 82, 42, 41, 47, 72, 
# 55, 69, 38, 27, 0, 14, 88, 12, 15, 3, 2, 11, 23]

# 426 g
# [99, 81, 123, 106, 68, 46, 66, 6, 89, 83, 4, 34, 90, 0, 125, 88, 140, 113, 
# 129, 80, 51, 41, 49, 108, 67, 98, 84, 37, 21, 76, 62, 52, 24, 74, 101, 19, 13, 
# 11, 79, 110, 60, 72, 114, 2, 20, 134, 27, 56, 116, 93, 31, 133, 85, 118, 50, 
# 26, 3, 120, 55, 121, 43, 70, 97, 40, 122, 54, 87, 96, 5, 25, 61, 91, 105, 1, 
# 18, 86, 75, 57, 64, 82, 29, 48, 63, 77, 47, 38, 78, 17, 45, 10, 39, 16, 102, 
# 69, 119, 104, 71, 22, 9, 32, 7, 36, 115, 53, 124, 23, 59, 44, 12, 42, 30, 8, 
# 35, 100, 112, 58, 33, 15, 28, 14, 94, 65]

# 877 RoeFlux_3d
# [96, 27, 126, 101, 75, 24, 118, 22, 3, 134, 8, 121, 97, 36, 82, 63, 81, 44, 
# 39, 94, 60, 85, 108, 42, 95, 88, 104, 61, 65, 28, 49, 128, 77, 136, 109, 38, 
# 64, 129, 68, 26, 78, 69, 18, 84, 105, 116, 37, 21, 113, 13, 124, 4, 86, 71, 
# 100, 34, 83, 80, 51, 58, 33, 11, 35, 5, 54, 123, 47, 56, 66, 92, 90, 15, 23, 
# 30, 127, 20, 93, 125, 40, 2, 9, 62, 72, 103, 120, 89, 59, 76, 111, 115, 106, 
# 119, 45, 112, 19, 67, 52, 10, 110, 102, 48, 98, 107, 31, 122, 114, 43, 87, 91, 
# 132, 50, 70, 7, 14, 0, 79, 32, 55, 17, 53, 117, 12, 99, 74, 6, 29, 130, 131, 
# 25, 73, 46, 57, 1, 41, 16]


parser = argparse.ArgumentParser()

parser.add_argument("--name", type=str, 
                    default="Test", help="Name of the experiment.")

parser.add_argument("--task", type=str,
                    default="RoeFlux_1d", help="Name of the task to run.")

parser.add_argument("--gpus", type=str, 
                    default="0", help="GPU ID's to use for training.")

parser.add_argument("--seed", type=int, 
                    default="250197", help="Random seed.")

parser.add_argument("--config_path", type=str, 
                    default=os.path.join(os.getcwd(), "config"), 
                    help="Path to the directory containing the configuration files.")

parser.add_argument("--wandb", type=str,
                    default="run", help="Wandb mode.")

args = parser.parse_args()

os.environ["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpus)
key = jrand.PRNGKey(args.seed)

config, graph, graph_shape, task_fn = setup_experiment(args.task, args.config_path)
mM_order, scores = make_benchmark_scores(graph)

parameters = config["hyperparameters"]
ENTROPY_WEIGHT = parameters["entropy_weight"]
VALUE_WEIGHT = parameters["value_weight"]
EPISODES = parameters["episodes"]
NUM_ENVS = parameters["num_envs"]
LR = parameters["lr"]

GAE_LAMBDA = parameters["ppo"]["gae_lambda"]
EPS = parameters["ppo"]["clip_param"]
MINIBATCHES = parameters["ppo"]["num_minibatches"]

ROLLOUT_LENGTH = int(graph_shape[-2] - graph_shape[-1]) # parameters["ppo"]["rollout_length"]
OBS_SHAPE = reduce(lambda x, y: x*y, graph.shape)
NUM_ACTIONS = graph.shape[-1] # ROLLOUT_LENGTH # TODO fix this
MINIBATCHSIZE = NUM_ENVS*ROLLOUT_LENGTH//MINIBATCHES

policy_key, value_key = jrand.split(key, 2)
# Larger models seem to help
policy_net = PolicyNet(graph_shape, 64, 5, 6, ff_dim=256, mlp_dims=[256, 256], key=policy_key)
value_net = ValueNet(graph_shape, 64, 4, 6, ff_dim=256, mlp_dims=[256, 128, 64], key=value_key)
p_init_key, v_init_key = jrand.split(key, 2)

init_fn = jnn.initializers.orthogonal(jnp.sqrt(2))

def init_weight(model, init_fn, key):
    is_linear = lambda x: isinstance(x, eqx.nn.Linear)
    get_weights = lambda m: [x.weight
                            for x in jax.tree_util.tree_leaves(m, is_leaf=is_linear)
                            if is_linear(x)]
    get_biases = lambda m: [x.bias
                            for x in jax.tree_util.tree_leaves(m, is_leaf=is_linear)
                            if is_linear(x) and x.bias is not None]
    weights = get_weights(model)
    biases = get_biases(model)
    new_weights = [init_fn(subkey, weight.shape)
                    for weight, subkey in zip(weights, jax.random.split(key, len(weights)))]
    new_biases = [jnp.zeros_like(bias) for bias in biases]
    new_model = eqx.tree_at(get_weights, model, new_weights)
    new_model = eqx.tree_at(get_biases, new_model, new_biases)
    return new_model


# Initialization could help with performance
policy_net = init_weight(policy_net, init_fn, p_init_key)
value_net = init_weight(value_net, init_fn, v_init_key)
    
    
run_config = {"seed": args.seed,
                "entropy_weight": ENTROPY_WEIGHT, 
                "value_weight": VALUE_WEIGHT, 
                "lr": LR,
                "episodes": EPISODES, 
                "batchsize": NUM_ENVS, 
                "gae_lambda": GAE_LAMBDA, 
                "eps": EPS, 
                "minibatches": MINIBATCHES, 
                "minibatchsize": MINIBATCHSIZE, 
                "obs_shape": OBS_SHAPE, 
                "num_actions": NUM_ACTIONS, 
                "rollout_length": ROLLOUT_LENGTH, 
                "fwd_fmas": scores[0], 
                "rev_fmas": scores[1], 
                "out_fmas": scores[2]}

wandb.login(key="local-84c6642fa82dc63629ceacdcf326632140a7a899", 
            host="https://wandb.fz-juelich.de")
wandb.init(entity="ja-lohoff", project="AlphaGrad", 
            group=args.task, config=run_config,
            mode=args.wandb)
wandb.run.name = "PPO_separate_networks_" + args.task + "_" + args.name


# Value scaling functions
def value_transform(x):
    return symlog(x)

def inverse_value_transform(x):
    return symexp(x)


# Definition of some RL metrics for diagnostics
def get_num_clipping_triggers(ratio):
    _ratio = jnp.where(ratio <= 1.+EPS, ratio, 0.)
    _ratio = jnp.where(ratio >= 1.-EPS, 1., 0.)
    return jnp.sum(_ratio)


@partial(jax.vmap, in_axes=(None, 0, 0, 0))
def get_log_probs_and_value(networks, state, action, key):
    policy_net, value_net = networks
    mask = 1. - state.at[1, 0, :].get()
    
    logits = policy_net(state, key=key)
    value = value_net(state, key=key)
    
    prob_dist = jnn.softmax(logits, axis=-1, where=mask, initial=mask.max())

    log_prob = jnp.log(prob_dist[action] + 1e-7)
    return log_prob, prob_dist, value, entropy(prob_dist)


@jax.jit
@jax.vmap
def get_returns(trajectories):
    rewards = trajectories[:, OBS_SHAPE+1]
    dones = trajectories[:, OBS_SHAPE+2]
    discounts = trajectories[:, 2*OBS_SHAPE+NUM_ACTIONS+4]
    inputs = jnp.stack([rewards, dones, discounts]).T
    
    def loop_fn(episodic_return, traj):
        reward = traj[0]
        done = traj[1]
        discount = traj[2]
        # Simplest advantage estimate
        # The advantage estimate has to be done with the states and actions 
        # sampled from the old policy due to the importance sampling formulation
        # of PPO
        done = 1. - done
        episodic_return = reward + discount*episodic_return*done
        return episodic_return, episodic_return
    
    _, output = lax.scan(loop_fn, 0., inputs[::-1])
    return output[::-1]


# Calculates advantages using generalized advantage estimation
@jax.jit
@jax.vmap
def get_advantages(trajectories):
    rewards = trajectories[:, OBS_SHAPE+1]
    dones = trajectories[:, OBS_SHAPE+2]
    values = trajectories[:, 2*OBS_SHAPE+3]
    next_values = jnp.roll(values, -1, axis=0)
    discounts = trajectories[:, 2*OBS_SHAPE+NUM_ACTIONS+4]
    inputs = jnp.stack([rewards, dones, values, next_values, discounts]).T
    
    def loop_fn(carry, traj):
        episodic_return, lastgaelam = carry
        reward = traj[0]
        done = traj[1]
        value = inverse_value_transform(traj[2])
        next_value = inverse_value_transform(traj[3])
        discount = traj[4]
        # Simplest advantage estimate
        # The advantage estimate has to be done with the states and actions 
        # sampled from the old policy due to the importance sampling formulation
        # of PPO
        done = 1. - done
        episodic_return = reward + discount*episodic_return*done
        delta = reward + next_value*discount*done - value
        advantage = delta + discount*GAE_LAMBDA*lastgaelam*done
        estim_return = advantage + value
        
        next_carry = (episodic_return, advantage)
        new_sample = jnp.array([episodic_return, estim_return, advantage])
        return next_carry, new_sample
    _, output = lax.scan(loop_fn, (0., 0.), inputs[::-1])
    return jnp.concatenate([trajectories, output[::-1]], axis=-1)
    
    
@jax.jit
def shuffle_and_batch(trajectories, key):
    size = NUM_ENVS*ROLLOUT_LENGTH//MINIBATCHES
    trajectories = trajectories.reshape(-1, trajectories.shape[-1])
    trajectories = jrand.permutation(key, trajectories, axis=0)
    return trajectories.reshape(MINIBATCHES, size, trajectories.shape[-1])


def init_carry(keys):
    graphs = jnp.tile(graph[jnp.newaxis, ...], (len(keys), 1, 1, 1))
    return graphs


# Implementation of the RL algorithm
@eqx.filter_jit
@partial(jax.vmap, in_axes=(None, None, 0, 0))
def rollout_fn(networks, rollout_length, init_carry, key):
    keys = jrand.split(key, rollout_length)
    policy_net, value_net = networks
    def step_fn(state, key):
        mask = 1. - state.at[1, 0, :].get()
        net_key, next_net_key, act_key = jrand.split(key, 3)
        
        logits = policy_net(state, key=net_key)
        prob_dist = jnn.softmax(logits, axis=-1, where=mask, initial=mask.max())
        
        distribution = distrax.Categorical(probs=prob_dist)
        action = distribution.sample(seed=act_key)
        
        next_state, reward, done = step(state, action)
        discount = 1.
        next_value = value_net(next_state, key=next_net_key)
        
        new_sample = jnp.concatenate((state.flatten(),
                                    jnp.array([action]), 
                                    jnp.array([reward]), 
                                    jnp.array([done]),
                                    next_state.flatten(), 
                                    jnp.array([next_value]),
                                    prob_dist, 
                                    jnp.array([discount]))) # (sars')
        
        return next_state, new_sample
    
    return lax.scan(step_fn, init_carry, keys)


def loss(networks, trajectories, keys):
    state = trajectories[:, :OBS_SHAPE]
    state = state.reshape(-1, *graph.shape)
    actions = trajectories[:, OBS_SHAPE]
    actions = jnp.int32(actions)
    
    rewards = trajectories[:, OBS_SHAPE+1]
    next_state = trajectories[:, OBS_SHAPE+3:2*OBS_SHAPE+3]
    next_state = next_state.reshape(-1, *graph.shape)
    
    old_prob_dist = trajectories[:, 2*OBS_SHAPE+4:2*OBS_SHAPE+NUM_ACTIONS+4]
    discounts = trajectories[:, 2*OBS_SHAPE+NUM_ACTIONS+4]
    episodic_returns = trajectories[:, 2*OBS_SHAPE+NUM_ACTIONS+5]
    returns = trajectories[:, 2*OBS_SHAPE+NUM_ACTIONS+6]
    advantages = trajectories[:, 2*OBS_SHAPE+NUM_ACTIONS+7]
    
    log_probs, prob_dist, values, entropies = get_log_probs_and_value(networks, state, actions, keys)
    _, _, next_values, _ = get_log_probs_and_value(networks, next_state, actions, keys)
    norm_adv = (advantages - jnp.mean(advantages)) / (jnp.std(advantages) + 1e-7)
    
    # Losses
    old_log_probs = jax.vmap(lambda dist, a: jnp.log(dist[a] + 1e-7))(old_prob_dist, actions)
    ratio = jnp.exp(log_probs - old_log_probs)
    
    num_triggers = get_num_clipping_triggers(ratio)
    trigger_ratio = num_triggers / len(ratio)
    
    clipping_objective = jnp.minimum(ratio*norm_adv, jnp.clip(ratio, 1.-EPS, 1.+EPS)*norm_adv)
    ppo_loss = jnp.mean(-clipping_objective)
    entropy_loss = jnp.mean(entropies)
    value_loss = .5*jnp.mean((values - value_transform(returns))**2)
    
    # Metrics
    dV = returns - rewards - discounts*inverse_value_transform(next_values) # assess fit quality
    fit_quality = jnp.mean(jnp.abs(dV))
    explained_var = explained_variance(advantages, returns)
    kl_div = jnp.mean(optax.kl_divergence(jnp.log(prob_dist + 1e-7), old_prob_dist))
    total_loss = ppo_loss
    total_loss += VALUE_WEIGHT*value_loss
    total_loss -= ENTROPY_WEIGHT*entropy_loss
    return total_loss, [kl_div, entropy_loss, fit_quality, explained_var,ppo_loss, 
                        VALUE_WEIGHT*value_loss, ENTROPY_WEIGHT*entropy_loss, 
                        total_loss, trigger_ratio]
    

@eqx.filter_jit
def train_agent(networks, opt_state, trajectories, keys):  
    grads, metrics = eqx.filter_grad(loss, has_aux=True)(networks, trajectories, keys)   
    updates, opt_state = optim.update(grads, opt_state)
    networks = eqx.apply_updates(networks, updates)
    return networks, opt_state, metrics


@eqx.filter_jit
def test_agent(network, rollout_length, keys):
    env_carry = init_carry(keys)
    _, trajectories = rollout_fn(network, rollout_length, env_carry, keys)
    returns = get_returns(trajectories)
    best_return = jnp.max(returns[:, 0], axis=-1)
    idx = jnp.argmax(returns[:, 0], axis=-1)
    best_act_seq = trajectories[idx, :, OBS_SHAPE]
    return best_return, best_act_seq, returns[:, 0]


model_key, key = jrand.split(key, 2)
model = (policy_net, value_net)


# Define optimizer
# TODO test L2 norm and stationary ADAM for better stability
schedule = LR # optax.cosine_decay_schedule(LR, 5000, 0.)
optim = optax.chain(optax.adam(schedule, b1=.9, eps=1e-7), 
                    optax.clip_by_global_norm(.5))
opt_state = optim.init(eqx.filter(model, eqx.is_inexact_array))


# Training loop
pbar = tqdm(range(EPISODES))
test_key, key = jrand.split(key, 2)
test_keys = jrand.split(test_key, 8)
samplecounts = 0

env_keys = jrand.split(key, NUM_ENVS)
env_carry = init_carry(env_keys)
best_global_return = jnp.max(-jnp.array(scores))
best_global_act_seq = None

elim_order_table = wandb.Table(columns=["episode", "return", "elimination order"])

for episode in pbar:
    subkey, key = jrand.split(key, 2)
    keys = jrand.split(key, NUM_ENVS)  
    env_carry = jax.jit(init_carry)(keys)
    env_carry, trajectories = rollout_fn(model, ROLLOUT_LENGTH, env_carry, keys)

    trajectories = get_advantages(trajectories)
    batches = shuffle_and_batch(trajectories, subkey)
    
    # We perform multiple descent steps on a subset of the same trajectory sample
    # This severely increases data efficiency
    # Furthermore, PPO utilizes the 'done' property to continue already running
    # environments
    for i in range(MINIBATCHES):
        subkeys = jrand.split(key, MINIBATCHSIZE)
        model, opt_state, metrics = train_agent(model, opt_state, batches[i], subkeys)   
    samplecounts += NUM_ENVS*ROLLOUT_LENGTH
    
    kl_div, policy_entropy, fit_quality, explained_var, ppo_loss, value_loss, entropy_loss, total_loss, clipping_trigger_ratio = metrics
    
    test_keys = jrand.split(key, NUM_ENVS)
    best_return, best_act_seq, returns = test_agent(model, ROLLOUT_LENGTH, test_keys)
    
    if best_return > best_global_return:
        best_global_return = best_return
        best_global_act_seq = best_act_seq
        print(f"New best return: {best_return}")
        vertex_elimination_order = [int(i) for i in best_act_seq]
        print(f"New best action sequence: {vertex_elimination_order}")
        elim_order_table.add_data(episode, best_return, np.array(best_act_seq))
    
    # Tracking different RL metrics
    wandb.log({"best_return": best_return,
               "mean_return": jnp.mean(returns),
                "KL divergence": kl_div,
                "entropy evolution": policy_entropy,
                "value function fit quality": fit_quality,
                "explained variance": explained_var,
                "sample count": samplecounts,
                "ppo loss": ppo_loss,
                "value loss": value_loss,
                "entropy loss": entropy_loss,
                "total loss": total_loss,
                "clipping trigger ratio": clipping_trigger_ratio})
        
    pbar.set_description(f"entropy: {policy_entropy:.4f}, best_return: {best_return}, mean_return: {jnp.mean(returns)}, fit_quality: {fit_quality:.2f}, expl_var: {explained_var:.4f}, kl_div: {kl_div:.4f}")
        
wandb.log({"Elimination order": elim_order_table})
vertex_elimination_order = [int(i) for i in best_act_seq]
print(f"Best vertex elimination sequence after {EPISODES} episodes is {vertex_elimination_order} with {best_global_return} multiplications.")
