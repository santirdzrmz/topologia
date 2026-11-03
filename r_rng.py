"""
Port of the pieces of R's random number machinery (R >= 3.6, default kinds:
Mersenne-Twister, Inversion, Rejection sampling) needed to reproduce
`set.seed(s)` + `sample()`, `runif()`, `rnorm()`, `rlnorm()` and `rpois()`
bit for bit in Python.

Ported from the R sources: src/main/RNG.c, src/main/random.c,
src/main/sort.c (revsort), src/nmath/{qnorm,snorm,sexp,rpois}.c
"""
import math
import numpy as np

_M32 = 0xFFFFFFFF
_I2_32M1 = 2.328306437080797e-10
_BUF = 8192


# ---------------------------------------------------------------------------
# qnorm (AS 241), lower tail, non-log, mu = 0, sigma = 1
# ---------------------------------------------------------------------------
def _qnorm(p):
    q = p - 0.5
    if abs(q) <= 0.425:
        r = 0.180625 - q * q
        return q * (((((((r * 2509.0809287301226727 +
                          33430.575583588128105) * r + 67265.770927008700853) * r +
                        45921.953931549871457) * r + 13731.693765509461125) * r +
                      1971.5909503065514427) * r + 133.14166789178437745) * r +
                    3.387132872796366608) / \
            (((((((r * 5226.495278852854561 +
                   28729.085735721942674) * r + 39307.89580009271061) * r +
                 21213.794301586595867) * r + 5394.1960214247511077) * r +
               687.1870074920579083) * r + 42.313330701600911252) * r + 1.0)

    lp = math.log(1.0 - p if q > 0 else p)
    r = math.sqrt(-lp)
    if r <= 5.0:
        r += -1.6
        val = (((((((r * 7.7454501427834140764e-4 +
                     .0227238449892691845833) * r + .24178072517745061177) *
                   r + 1.27045825245236838258) * r +
                  3.64784832476320460504) * r + 5.7694972214606914055) *
                r + 4.6303378461565452959) * r +
               1.42343711074968357734) / \
            (((((((r * 1.05075007164441684324e-9 + 5.475938084995344946e-4) *
                  r + .0151986665636164571966) * r +
                 .14810397642748007459) * r + .68976733498510000455) *
               r + 1.6763848301838038494) * r +
              2.05319162663775882187) * r + 1.0)
    else:
        r += -5.0
        val = (((((((r * 2.01033439929228813265e-7 +
                     2.71155556874348757815e-5) * r +
                    .0012426609473880784386) * r + .026532189526576123093) *
                  r + .29656057182850489123) * r +
                 1.7848265399172913358) * r + 5.4637849111641143699) *
               r + 6.6579046435011037772) / \
            (((((((r * 2.04426310338993978564e-15 + 1.4215117583164458887e-7) *
                  r + 1.8463183175100546818e-5) * r +
                 7.868691311456132591e-4) * r + .0148753612908506148525) *
               r + .13692988092273580531) * r +
              .59983220655588793769) * r + 1.0)
    return -val if q < 0.0 else val


# ---------------------------------------------------------------------------
# revsort: heapsort into descending order, carrying an index vector
# ---------------------------------------------------------------------------
def _revsort(a, ib):
    n = len(a)
    if n <= 1:
        return
    a.insert(0, None)
    ib.insert(0, None)
    l = (n >> 1) + 1
    ir = n
    while True:
        if l > 1:
            l -= 1
            ra = a[l]
            ii = ib[l]
        else:
            ra = a[ir]
            ii = ib[ir]
            a[ir] = a[1]
            ib[ir] = ib[1]
            ir -= 1
            if ir == 1:
                a[1] = ra
                ib[1] = ii
                break
        i = l
        j = l << 1
        while j <= ir:
            if j < ir and a[j] > a[j + 1]:
                j += 1
            if ra > a[j]:
                a[i] = a[j]
                ib[i] = ib[j]
                i = j
                j += i
            else:
                j = ir + 1
        a[i] = ra
        ib[i] = ii
    del a[0]
    del ib[0]


_FACT = [1., 1., 2., 6., 24., 120., 720., 5040., 40320., 362880.]
_EXP_Q = [0.6931471805599453, 0.9333736875190459, 0.9888777961838675,
          0.9984959252914960, 0.9998292811061389, 0.9999833164100727,
          0.9999985691438767, 0.9999998906925558, 0.9999999924734159,
          0.9999999995283275, 0.9999999999728814, 0.9999999999985598,
          0.9999999999999289, 0.9999999999999968, 0.9999999999999999,
          1.0000000000000000]
_M_1_SQRT_2PI = 0.398942280401432677939946059934


class RRandom:
    """Stateful generator mimicking R's global RNG after `set.seed(seed)`."""

    def __init__(self, seed):
        self.set_seed(seed)

    # -- seeding / uniform stream ------------------------------------------
    def set_seed(self, seed):
        seed &= _M32
        for _ in range(50):
            seed = (69069 * seed + 1) & _M32
        i_seed = []
        for _ in range(625):
            seed = (69069 * seed + 1) & _M32
            i_seed.append(seed)
        # i_seed[0] is `mti` (forced to N = 624); the MT state is i_seed[1:]
        bg = np.random.MT19937()
        bg.state = {"bit_generator": "MT19937",
                    "state": {"key": np.array(i_seed[1:], dtype=np.uint32),
                              "pos": 624}}
        self._bg = bg
        self._buf = []
        self._pos = 0
        # rpois persistent state
        self._muprev = 0.0
        self._muprev2 = 0.0
        self._pp = [0.0] * 36
        self._l = 0
        self._m = 0

    def unif_rand(self):
        if self._pos >= len(self._buf):
            self._buf = self._bg.random_raw(_BUF).tolist()
            self._pos = 0
        x = self._buf[self._pos] * 2.3283064365386963e-10
        self._pos += 1
        if x <= 0.0:
            return 0.5 * _I2_32M1
        if 1.0 - x <= 0.0:
            return 1.0 - 0.5 * _I2_32M1
        return x

    def norm_rand(self):
        big = 134217728
        u1 = self.unif_rand()
        u1 = int(big * u1) + self.unif_rand()
        return _qnorm(u1 / big)

    def exp_rand(self):
        q = _EXP_Q
        a = 0.0
        u = self.unif_rand()
        while u <= 0.0 or u >= 1.0:
            u = self.unif_rand()
        while True:
            u += u
            if u > 1.0:
                break
            a += q[0]
        u -= 1.0
        if u <= q[0]:
            return a + u
        i = 0
        ustar = self.unif_rand()
        umin = ustar
        while True:
            ustar = self.unif_rand()
            if umin > ustar:
                umin = ustar
            i += 1
            if u <= q[i]:
                break
        return a + umin * q[0]

    # -- integer sampling ----------------------------------------------------
    def _rbits(self, bits):
        v = 0
        n = 0
        while n <= bits:
            v1 = int(math.floor(self.unif_rand() * 65536))
            v = 65536 * v + v1
            n += 16
        return v & ((1 << bits) - 1)

    def unif_index(self, dn):
        if dn <= 0:
            return 0
        bits = int(math.ceil(math.log2(dn)))
        while True:
            dv = self._rbits(bits)
            if dv < dn:
                return dv

    def sample_int(self, n, size=None, replace=False, prob=None):
        """R's sample.int(n, size, replace, prob); returns 1-based ints."""
        if size is None:
            size = n
        if prob is not None:
            return self._sample_prob(n, size, replace, prob)
        if not replace and size > n:
            raise ValueError("cannot take a sample larger than the population")
        if n > 1e7 and not replace and size <= n / 2:
            # hashing path (sample2): rejection of duplicates
            seen, out = set(), []
            for _ in range(size):
                while True:
                    v = self.unif_index(n) + 1
                    if v not in seen:
                        break
                seen.add(v)
                out.append(v)
            return out
        if replace or size < 2:
            return [self.unif_index(n) + 1 for _ in range(size)]
        x = list(range(n))
        out = []
        for _ in range(size):
            j = self.unif_index(n)
            out.append(x[j] + 1)
            n -= 1
            x[j] = x[n]
        return out

    def _sample_prob(self, n, size, replace, prob):
        if not replace:
            raise NotImplementedError("prob sampling only with replacement")
        tot = math.fsum(prob)
        p = [pi / tot for pi in prob]
        if sum(1 for pi in p if n * pi > 0.1) > 200:
            raise NotImplementedError("Walker alias method not ported")
        perm = list(range(1, n + 1))
        _revsort(p, perm)
        for i in range(1, n):
            p[i] += p[i - 1]
        out = []
        for _ in range(size):
            ru = self.unif_rand()
            j = 0
            while j < n - 1 and not (ru <= p[j]):
                j += 1
            out.append(perm[j])
        return out

    def sample(self, x, size=None, replace=False, prob=None):
        """R's sample(x, size, replace, prob) for a sequence x (len > 1)."""
        idx = self.sample_int(len(x), size, replace, prob)
        return [x[i - 1] for i in idx]

    # -- continuous distributions ---------------------------------------------
    def runif(self, n, a=0.0, b=1.0):
        return [a + (b - a) * self.unif_rand() for _ in range(n)]

    def rnorm(self, n, mean=0.0, sd=1.0):
        mean = list(mean) if hasattr(mean, "__len__") else [mean] * n
        sd = list(sd) if hasattr(sd, "__len__") else [sd] * n
        return [mean[i] + sd[i] * self.norm_rand() for i in range(n)]

    def rlnorm(self, n, meanlog=0.0, sdlog=1.0):
        return [math.exp(meanlog + sdlog * self.norm_rand()) for _ in range(n)]

    # -- Poisson ----------------------------------------------------------------
    def _step_f(self, mu, pois, fk, difmuk, s, omega, c3, c2, c1, c0):
        a0, a1, a2, a3 = -0.5, 0.3333333, -0.2500068, 0.2000118
        a4, a5, a6, a7 = -0.1661269, 0.1421878, -0.1384794, 0.1250060
        one_12 = 0.0833333333333333333
        if pois < 10:
            px = -mu
            py = math.pow(mu, pois) / _FACT[int(pois)]
        else:
            de = one_12 / fk
            de = de * (1.0 - 4.8 * de * de)
            v = difmuk / fk
            if abs(v) <= 0.25:
                px = fk * v * v * (((((((a7 * v + a6) * v + a5) * v + a4) *
                                      v + a3) * v + a2) * v + a1) * v + a0) - de
            else:
                px = fk * math.log(1.0 + v) - difmuk - de
            py = _M_1_SQRT_2PI / math.sqrt(fk)
        x = (0.5 - difmuk) / s
        x *= x
        fx = -0.5 * x
        fy = omega * (((c3 * x + c2) * x + c1) * x + c0)
        return px, py, fx, fy

    def rpois1(self, mu):
        """One draw of R's rpois(1, mu)."""
        if mu <= 0.0:
            return 0.0
        one_7 = 0.1428571428571428571
        one_24 = 0.0416666666666666667
        big_mu = mu >= 10.0
        new_big_mu = False

        if not (big_mu and mu == self._muprev):
            if big_mu:
                new_big_mu = True
                self._muprev = mu
                self._s = math.sqrt(mu)
                self._d = 6.0 * mu * mu
                self._big_l = math.floor(mu - 1.1484)
            else:
                if mu != self._muprev:
                    self._muprev = mu
                    self._m = max(1, int(mu))
                    self._l = 0
                    self._q = self._p0 = self._p = math.exp(-mu)
                pp = self._pp
                while True:
                    u = self.unif_rand()
                    if u <= self._p0:
                        return 0.0
                    if self._l != 0:
                        k = 1 if u <= 0.458 else min(self._l, self._m)
                        while k <= self._l:
                            if u <= pp[k]:
                                return float(k)
                            k += 1
                        if self._l == 35:
                            continue
                    self._l += 1
                    for k in range(self._l, 36):
                        self._p *= mu / k
                        self._q += self._p
                        pp[k] = self._q
                        if u <= self._q:
                            self._l = k
                            return float(k)
                    self._l = 35

        s, d, big_l = self._s, self._d, self._big_l
        g = mu + s * self.norm_rand()
        pois = -1.0
        fk = difmuk = 0.0
        u = 0.0
        if g >= 0.0:
            pois = math.floor(g)
            if pois >= big_l:
                return pois
            fk = pois
            difmuk = mu - fk
            u = self.unif_rand()
            if d * u >= difmuk * difmuk * difmuk:
                return pois

        if new_big_mu or mu != self._muprev2:
            self._muprev2 = mu
            self._omega = _M_1_SQRT_2PI / s
            b1 = one_24 / mu
            b2 = 0.3 * b1 * b1
            self._c3 = one_7 * b1 * b2
            self._c2 = b2 - 15.0 * self._c3
            self._c1 = b1 - 6.0 * b2 + 45.0 * self._c3
            self._c0 = 1.0 - b1 + 3.0 * b2 - 15.0 * self._c3
            self._c = 0.1069 / mu
        omega, c3, c2, c1, c0, c = (self._omega, self._c3, self._c2,
                                    self._c1, self._c0, self._c)

        if g >= 0.0:
            px, py, fx, fy = self._step_f(mu, pois, fk, difmuk, s, omega,
                                          c3, c2, c1, c0)
            if fy - u * fy <= py * math.exp(px - fx):
                return pois

        while True:
            E = self.exp_rand()
            u = 2 * self.unif_rand() - 1.0
            t = 1.8 + (abs(E) if u >= 0 else -abs(E))
            if t > -0.6744:
                pois = math.floor(mu + s * t)
                fk = pois
                difmuk = mu - fk
                px, py, fx, fy = self._step_f(mu, pois, fk, difmuk, s, omega,
                                              c3, c2, c1, c0)
                if c * abs(u) <= py * math.exp(px + E) - fy * math.exp(fx + E):
                    return pois
