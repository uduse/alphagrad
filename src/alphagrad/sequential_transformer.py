from typing import Sequence

import jax
import jax.numpy as jnp
import jax.random as jrand

from chex import Array, PRNGKey
import equinox as eqx
from equinox import static_field

from alphagrad.transformer import MLP
from alphagrad.transformer import Encoder
from alphagrad.transformer import PositionalEncoder


class SequentialTransformer(eqx.Module):
    num_heads: int
    pos_enc: PositionalEncoder
    encoder: Encoder
    policy_enc: Encoder
    policy_head: MLP
    value_head: MLP
    global_token: Array
    global_token_mask_x: Array = static_field()
    global_token_mask_y: Array = static_field()
    
    def __init__(self, 
                in_dim: int,
                seq_len: int,
                num_layers: int,
                num_heads: int,
                ff_dim: int = 1024,
                num_layers_policy: int = 2,
                policy_ff_dims: Sequence[int] = [512, 256],
                value_ff_dims: Sequence[int] = [1024, 512],
                key: PRNGKey = None) -> None:
        super().__init__()  
        self.num_heads = num_heads      
        e_key, p_key, pe_key, v_key, t_key = jrand.split(key, 5)
        
        # Here we use seq_len + 1 because of the global class token
        self.pos_enc = PositionalEncoder(in_dim, seq_len+1)
        
        self.encoder = Encoder(num_layers=num_layers,
                                num_heads=num_heads,
                                in_dim=in_dim,
                                ff_dim=ff_dim,
                                key=e_key)
        
        self.policy_enc = Encoder(num_layers=num_layers_policy,
                                num_heads=num_heads,
                                in_dim=in_dim,
                                ff_dim=ff_dim,
                                key=pe_key)
        
        self.global_token = jrand.normal(t_key, (in_dim, 1))
        self.global_token_mask_x = jnp.ones((seq_len, 1))
        self.global_token_mask_y = jnp.ones((1, seq_len+1))
        self.policy_head = MLP(in_dim, seq_len, policy_ff_dims, key=p_key)
        self.value_head = MLP(in_dim, 1, value_ff_dims, key=v_key)
        
    def __call__(self, xs: Array, mask: Array = None, key: PRNGKey = None) -> Array:
        e_key, p_key = jrand.split(key, 2)
            
        # Add global token to input
        xs = jnp.concatenate((self.global_token, xs), axis=-1)
        mask = jnp.concatenate((self.global_token_mask_x, mask), axis=-1)
        mask = jnp.concatenate((self.global_token_mask_y, mask), axis=-2)
        
        # Transpose inputs for equinox attention mechanism
        xs = self.pos_enc(xs).T
        mask = mask.T
        
        # Replicate mask and apply encoder
        replicated_mask = jnp.tile(mask[jnp.newaxis, :, :], (self.num_heads, 1, 1))
        xs = self.encoder(xs, mask=replicated_mask, key=e_key)
        
        global_token_xs = xs[0]
        value = self.value_head(global_token_xs)
        
        policy = self.policy_enc(xs, mask=replicated_mask, key=p_key)
        global_policy_token = policy[0]
        policy = self.policy_head(global_policy_token)
        return jnp.concatenate((value, policy))


class SequentialTransformerModel(eqx.Module):
    embedding: eqx.nn.Conv2d
    projection: Array
    output_token: Array
    transformer: SequentialTransformer
    
    def __init__(self, 
                info: Sequence[int],
                embedding_dim: int,
                num_layers: int,
                num_heads: int,
                key: PRNGKey = None,
                **kwargs) -> None:
        super().__init__()
        embed_key, token_key, proj_key, tf_key = jrand.split(key, 4)
        self.embedding = eqx.nn.Conv2d(info[1], info[1], (5, 1), stride=(1, 1), key=embed_key)
        self.projection = jrand.normal(proj_key, (info[0]+info[1], embedding_dim))
        self.output_token = jrand.normal(token_key, (info[0]+info[1], 1))
        self.transformer = SequentialTransformer(embedding_dim,
                                                info[1], 
                                                num_layers, 
                                                num_heads, 
                                                key=tf_key, 
                                                **kwargs)
    
    def __call__(self, xs: Array, key: PRNGKey = None) -> Array:
        output_mask = xs.at[2, 0, :].get()
        vertex_mask = xs.at[1, 0, :].get() - output_mask
        attn_mask = jnp.logical_or(vertex_mask.reshape(1, -1), vertex_mask.reshape(-1, 1))

        output_token_mask = jnp.where(xs.at[2, 0, :].get() > 0, self.output_token, 0.)
        edges = xs.at[:, 1:, :].get() + output_token_mask[jnp.newaxis, :, :]
        edges = edges.astype(jnp.float32)
        embeddings = self.embedding(edges.transpose(2, 0, 1)).squeeze()
        embeddings = jax.vmap(jnp.matmul, in_axes=(0, None))(embeddings, self.projection)
        return self.transformer(embeddings.T, mask=attn_mask, key=key)
    
