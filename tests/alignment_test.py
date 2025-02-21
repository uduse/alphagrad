import unittest

import jax
import jax.nn as jnn
import jax.numpy as jnp
import jax.random as jrand

from graphax import jacve
from graphax.examples import (Simple, Helmholtz, Perceptron, Encoder, RoeFlux_1d,
                                f, g, RoeFlux_3d, RobotArm_6DOF, EncoderDecoder,
                                PropaneCombustion, HumanHeartDipole)
from graphax.examples.deep_learning import encoder_block
from alphagrad.vertexgame import (cross_country, forward, reverse, 
                                make_graph, minimal_markowitz)


def test_function(f, *xs):    
    jaxpr = jax.make_jaxpr(f)(*xs)
    print(jaxpr)
    
    graph = make_graph(f, *xs)
    _, fwd_fmas = jax.jit(forward)(graph)
    _, rev_fmas = jax.jit(reverse)(graph)
    
    order = jax.jit(minimal_markowitz, static_argnums=1)(graph, int(graph[0, 0, 1]))
    order = [int(o) for o in order]
    _, cc_fmas = jax.jit(cross_country)(order, graph)
    
    argnums = list(range(len(xs)))
    _, _fmas = jax.jit(jacve(f, order="fwd", argnums=argnums, count_ops=True))(*xs)
    gx_fwd_fmas = _fmas["num_muls"]
    _, _fmas = jax.jit(jacve(f, order="rev", argnums=argnums, count_ops=True))(*xs)
    gx_rev_fmas = _fmas["num_muls"]
    _, _fmas = jax.jit(jacve(f, order=order, argnums=argnums, count_ops=True))(*xs)
    gx_cc_fmas = _fmas["num_muls"]
    
    print("###")
    print(fwd_fmas, "graphax result:", gx_fwd_fmas)
    print(rev_fmas, "graphax result:", gx_rev_fmas)
    print(cc_fmas, "graphax result:", gx_cc_fmas)
    print("###")
    # 
    if fwd_fmas == gx_fwd_fmas and rev_fmas == gx_rev_fmas and cc_fmas == gx_cc_fmas:
        return True
    else:
        return False
    
    
class GraphaxAlignmentTest(unittest.TestCase):
    # # Scalar function tests
    # def test_Simple(self):
    #     result = test_function(Simple, 1., 2.)
    #     self.assertTrue(result)
        
    # def test_RoeFlux_1d(self):
    #     xs = [.01, .02, .02, .01, .03, .03]
    #     result = test_function(RoeFlux_1d, *xs)
    #     self.assertTrue(result)
        
    # def test_RobotArm_6DOF(self):
    #     xs = [.01, .02, .02, .01, .03, .03]
    #     result = test_function(RobotArm_6DOF, *xs)
    #     self.assertTrue(result)
        
    # def test_g(self):
    #     xs = [jnp.array([1.])]*15
    #     result = test_function(g, *xs)
    #     self.assertTrue(result)
    
    # def test_HumanHeartDipole(self):
    #     xs = [.15]*8
    #     result = test_function(HumanHeartDipole, *xs)
    #     self.assertTrue(result)


    # def test_PropaneCombustion(self):
    #     xs = [.15]*11
    #     result = test_function(PropaneCombustion, *xs)
    #     self.assertTrue(result)
        
    # # Vector function tests
    # def test_Helmholtz(self):
    #     xs = jnp.array([.1, .1, .2, .2])
    #     result = test_function(Helmholtz, xs)
    #     self.assertTrue(result)
        
    # def test_Perceptron(self):
    #     key = jrand.PRNGKey(1234)

    #     x = jnp.ones(4)
    #     y = jrand.normal(key, (4,))

    #     w1key, b1key, key = jrand.split(key, 3)
    #     W1 = jrand.normal(w1key, (8, 4))
    #     b1 = jrand.normal(b1key, (8,))

    #     w2key, b2key, key = jrand.split(key, 3)
    #     W2 = jrand.normal(w2key, (4, 8))
    #     b2 = jrand.normal(b2key, (4,))

    #     xs = (x, y, W1, b1, W2, b2, 0., 1.)
    #     result = test_function(Perceptron, *xs)
    #     self.assertTrue(result)
        
    # def test_attention(self):
    #     key = jrand.PRNGKey(250197)
    #     x = jnp.ones((4, 4))

    #     wqkey, wkkey, wvkey, key = jrand.split(key, 4)
    #     WQ1 = jrand.normal(wqkey, (4, 4))
    #     WK1 = jrand.normal(wkkey, (4, 4))
    #     WV1 = jrand.normal(wvkey, (4, 4))
            
    #     xs = (x, WQ1, WK1, WV1)

    #     def attn_fn(x, Wq, Wk, Wv):
    #         q = Wq @ x
    #         k = Wk @ x
    #         v = Wv @ x
    #         a = jnn.softmax(q.T @ k, axis=1)
    #         return a @ v
        
    #     result = test_function(attn_fn, *xs)
    #     self.assertTrue(result)
        
    # def test_encoder_block(self):
    #     key = jrand.PRNGKey(250197)
    #     x = jnp.ones((4, 4))

    #     wqkey, wkkey, wvkey, key = jrand.split(key, 4)
    #     WQ1 = jrand.normal(wqkey, (4, 4))
    #     WK1 = jrand.normal(wkkey, (4, 4))
    #     WV1 = jrand.normal(wvkey, (4, 4))
        
    #     wkey, bkey = jrand.split(key, 2)
    #     W = jrand.normal(wkey, (4, 4))
    #     b = jrand.normal(bkey, (4, 1))
            
    #     xs = (x, WQ1, WK1, WV1, W, b, jnp.array([[1.]]), jnp.array([[0.]]))     
    #     result = test_function(encoder_block, *xs)
    #     self.assertTrue(result)
        
    def test_Encoder(self):
        key = jrand.PRNGKey(250197)
        x = jnp.ones((4, 4))
        y = jrand.normal(key, (2, 4))

        wq1key, wk1key, wv1key, key = jrand.split(key, 4)
        WQ1 = jrand.normal(wq1key, (4, 4))
        WK1 = jrand.normal(wk1key, (4, 4))
        WV1 = jrand.normal(wv1key, (4, 4))

        wq2key, wk2key, wv2key, key = jrand.split(key, 4)
        WQ2 = jrand.normal(wq2key, (4, 4))
        WK2 = jrand.normal(wk2key, (4, 4))
        WV2 = jrand.normal(wv2key, (4, 4))

        w1key, w2key, b1key, b2key = jrand.split(key, 4)
        W1 = jrand.normal(w1key, (4, 4))
        b1 = jrand.normal(b1key, (4,))

        W2 = jrand.normal(w2key, (2, 4))
        b2 = jrand.normal(b2key, (2, 1))
        
        xs = (x, y, WQ1, WQ2, WK1, WK2, WV1, WV2, W1, W2, b1, b2, 0., 1., 0., 1.)
        result = test_function(Encoder, *xs)
        self.assertTrue(result)
        
    # def test_EncoderDecoder(self):
    #     key = jrand.PRNGKey(250197)
    #     x = jnp.ones((4, 4))
    #     y = jrand.normal(key, (2, 4))

    #     wq1key, wk1key, wv1key, key = jrand.split(key, 4)
    #     WQ1 = jrand.normal(wq1key, (4, 4))
    #     WK1 = jrand.normal(wk1key, (4, 4))
    #     WV1 = jrand.normal(wv1key, (4, 4))

    #     wq2key, wk2key, wv2key, key = jrand.split(key, 4)
    #     WQ2 = jrand.normal(wq2key, (4, 4))
    #     WK2 = jrand.normal(wk2key, (4, 4))
    #     WV2 = jrand.normal(wv2key, (4, 4))

    #     w1key, w2key, b1key, b2key = jrand.split(key, 4)
    #     W1 = jrand.normal(w1key, (4, 4))
    #     b1 = jrand.normal(b1key, (4,))

    #     W2 = jrand.normal(w2key, (2, 4))
    #     b2 = jrand.normal(b2key, (2, 1))
        
    #     xs = (x, y, WQ1, WQ2, WK1, WK2, WV1, WV2, W1, W2, b1, b2, 0., 1., 0., 1.)
    #     jaxpr = jax.make_jaxpr(Encoder)(*xs)
    #     print(jaxpr)
    #     result = test_function(Encoder, *xs)
    #     self.assertTrue(result)
    
    # def test_f(self):
    #     key = jrand.PRNGKey(250197)
    #     a = jrand.uniform(key, (4,))
    #     b = jrand.uniform(key, (2, 3))
    #     c = jrand.uniform(key, (4, 4))
    #     d = jrand.uniform(key, (4, 1))
    #     xs = (a, b, c, d)
        
    #     jaxpr = jax.make_jaxpr(f)(*xs)
    #     print(jaxpr)
    #     result = test_function(f, *xs)
    #     self.assertTrue(result)
        
    # def test_RoeFlux_3d(self):
    #     ul0 = jnp.array([.1])
    #     ul = jnp.array([.1, .2, .3])
    #     ul4 = jnp.array([.5])
    #     ur0 = jnp.array([.2])
    #     ur = jnp.array([.2, .2, .4])
    #     ur4 = jnp.array([.6])
        
    #     xs = (ul0, ul, ul4, ur0, ur, ur4)
    #     result = test_function(RoeFlux_3d, *xs)
    #     print(result)
    #     self.assertTrue(result)
                
    # vmap and batching tests 
    
        
if __name__ == '__main__':
    unittest.main()

