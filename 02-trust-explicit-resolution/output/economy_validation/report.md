# Funded resolution game: publication validation

171 configurations × 20 seeds × 250 episodes = 855,000 episodes.

Market claims sum to the collateral pool under each outcome. Fees are prepaid; bond transfers and resource costs balance in every episode. Checks occur on honest and false proposals. Detection is 1 for the NONE composition model. No source-resilience probabilities enter this game.

Maximum cash conservation residual: 1.49569e-12. Maximum absolute standardized Monte Carlo error against exact conditional wrong-outcome probability: 1.8755.

Rates below are per episode; deferred episodes remain a separate endpoint. The complete CSV also reports wrong/submitted rates, Wilson intervals, work costs, capital costs, expected probabilities, and payout redistribution. Paired treatment differences and seed-cluster 95% t intervals are in paired_contrasts.csv. The twenty-seed intervals quantify Monte Carlo uncertainty only.

| Configuration | Wrong | Submitted | Attack | Checks | Resource cost |
|---|---:|---:|---:|---:|---:|
| bond_scaling/L50-lazy/flat10 | 0.2108 | 1.0000 | 0.2692 | 0.844 | 2.437 |
| bond_scaling/L50-lazy/rho0.05 | 0.2108 | 1.0000 | 0.2692 | 0.844 | 2.437 |
| bond_scaling/L50-lazy/rho0.1 | 0.2108 | 1.0000 | 0.2692 | 0.844 | 2.437 |
| bond_scaling/L50-lazy/rho0.15 | 0.2108 | 1.0000 | 0.2692 | 0.844 | 2.437 |
| bond_scaling/L50-lazy/rho0.25 | 0.1950 | 1.0000 | 0.2436 | 0.844 | 2.434 |
| bond_scaling/L50-lazy/rho0.5 | 0.0072 | 1.0000 | 0.0104 | 0.844 | 2.423 |
| bond_scaling/L50-attentive/flat10 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50-attentive/rho0.05 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50-attentive/rho0.1 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50-attentive/rho0.15 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50-attentive/rho0.25 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50-attentive/rho0.5 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L500-lazy/flat10 | 0.3054 | 1.0000 | 0.4852 | 0.844 | 2.469 |
| bond_scaling/L500-lazy/rho0.05 | 0.3044 | 1.0000 | 0.4804 | 0.844 | 2.468 |
| bond_scaling/L500-lazy/rho0.1 | 0.2938 | 1.0000 | 0.4442 | 0.844 | 2.461 |
| bond_scaling/L500-lazy/rho0.15 | 0.2774 | 1.0000 | 0.4024 | 0.844 | 2.455 |
| bond_scaling/L500-lazy/rho0.25 | 0.2268 | 1.0000 | 0.2964 | 0.844 | 2.440 |
| bond_scaling/L500-lazy/rho0.5 | 0.0266 | 1.0000 | 0.0356 | 0.844 | 2.424 |
| bond_scaling/L500-attentive/flat10 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L500-attentive/rho0.05 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L500-attentive/rho0.1 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L500-attentive/rho0.15 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L500-attentive/rho0.25 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L500-attentive/rho0.5 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L5000-lazy/flat10 | 0.6306 | 1.0000 | 1.0000 | 0.851 | 2.522 |
| bond_scaling/L5000-lazy/rho0.05 | 0.3050 | 1.0000 | 0.4834 | 0.844 | 2.469 |
| bond_scaling/L5000-lazy/rho0.1 | 0.2960 | 1.0000 | 0.4512 | 0.844 | 2.463 |
| bond_scaling/L5000-lazy/rho0.15 | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| bond_scaling/L5000-lazy/rho0.25 | 0.2296 | 1.0000 | 0.3032 | 0.844 | 2.441 |
| bond_scaling/L5000-lazy/rho0.5 | 0.0298 | 1.0000 | 0.0402 | 0.844 | 2.425 |
| bond_scaling/L5000-attentive/flat10 | 0.0494 | 1.0000 | 0.0000 | 7.964 | 6.232 |
| bond_scaling/L5000-attentive/rho0.05 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L5000-attentive/rho0.1 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L5000-attentive/rho0.15 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L5000-attentive/rho0.25 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L5000-attentive/rho0.5 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50000-lazy/flat10 | 0.6306 | 1.0000 | 1.0000 | 0.851 | 2.522 |
| bond_scaling/L50000-lazy/rho0.05 | 0.3050 | 1.0000 | 0.4836 | 0.844 | 2.469 |
| bond_scaling/L50000-lazy/rho0.1 | 0.2962 | 1.0000 | 0.4522 | 0.844 | 2.463 |
| bond_scaling/L50000-lazy/rho0.15 | 0.2822 | 1.0000 | 0.4132 | 0.844 | 2.456 |
| bond_scaling/L50000-lazy/rho0.25 | 0.2300 | 1.0000 | 0.3038 | 0.844 | 2.441 |
| bond_scaling/L50000-lazy/rho0.5 | 0.0300 | 1.0000 | 0.0404 | 0.844 | 2.425 |
| bond_scaling/L50000-attentive/flat10 | 0.0494 | 1.0000 | 0.0000 | 7.964 | 6.232 |
| bond_scaling/L50000-attentive/rho0.05 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50000-attentive/rho0.1 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50000-attentive/rho0.15 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50000-attentive/rho0.25 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_scaling/L50000-attentive/rho0.5 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| bond_cap/L5000-mixed/uncapped | 0.3186 | 1.0000 | 0.4402 | 0.840 | 2.452 |
| bond_cap/L5000-mixed/cap250 | 0.3048 | 1.0000 | 0.4834 | 0.844 | 2.469 |
| bond_cap/L5000-mixed/cap500 | 0.3144 | 1.0000 | 0.4584 | 0.840 | 2.458 |
| bond_cap/L5000-mixed/cap1000 | 0.3186 | 1.0000 | 0.4402 | 0.840 | 2.452 |
| bond_cap/L5000-mixed/cap5000 | 0.3186 | 1.0000 | 0.4402 | 0.840 | 2.452 |
| bond_cap/L50000-mixed/uncapped | 0.4242 | 0.9808 | 0.4760 | 0.827 | 2.389 |
| bond_cap/L50000-mixed/cap250 | 0.6306 | 1.0000 | 1.0000 | 0.851 | 2.522 |
| bond_cap/L50000-mixed/cap500 | 0.6616 | 1.0000 | 1.0000 | 0.849 | 2.513 |
| bond_cap/L50000-mixed/cap1000 | 0.3422 | 1.0000 | 0.4906 | 0.842 | 2.460 |
| bond_cap/L50000-mixed/cap5000 | 0.4158 | 0.9978 | 0.4936 | 0.840 | 2.436 |
| window/lazy/w2 | 0.4664 | 1.0000 | 0.4852 | 0.078 | 2.044 |
| window/lazy/w12 | 0.3788 | 1.0000 | 0.4836 | 0.448 | 2.252 |
| window/lazy/w24 | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| window/lazy/w48 | 0.1586 | 1.0000 | 0.2356 | 1.446 | 2.743 |
| window/lazy/w72 | 0.1252 | 1.0000 | 0.2148 | 1.916 | 2.982 |
| window/attentive/w2 | 0.0608 | 1.0000 | 0.1292 | 1.616 | 2.826 |
| window/attentive/w12 | 0.0000 | 1.0000 | 0.0000 | 6.122 | 5.061 |
| window/attentive/w24 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| window/attentive/w48 | 0.0000 | 1.0000 | 0.0000 | 8.832 | 6.416 |
| window/attentive/w72 | 0.0000 | 1.0000 | 0.0000 | 8.965 | 6.482 |
| window/stake/w2 | 0.4672 | 1.0000 | 0.4852 | 0.072 | 2.041 |
| window/stake/w12 | 0.3874 | 1.0000 | 0.4852 | 0.424 | 2.238 |
| window/stake/w24 | 0.3168 | 1.0000 | 0.4852 | 0.821 | 2.455 |
| window/stake/w48 | 0.0954 | 1.0000 | 0.1966 | 1.548 | 2.800 |
| window/stake/w72 | 0.0048 | 1.0000 | 0.0098 | 2.186 | 3.094 |
| accuracy/lazy/a0.7 | 0.3524 | 1.0000 | 0.4816 | 0.844 | 2.468 |
| accuracy/lazy/a0.9 | 0.2946 | 1.0000 | 0.4242 | 0.844 | 2.458 |
| accuracy/lazy/a0.95 | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| accuracy/lazy/a0.99 | 0.2696 | 1.0000 | 0.3956 | 0.844 | 2.454 |
| accuracy/lazy/a1 | 0.2662 | 1.0000 | 0.3910 | 0.844 | 2.453 |
| accuracy/attentive/a0.7 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| accuracy/attentive/a0.9 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| accuracy/attentive/a0.95 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| accuracy/attentive/a0.99 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| accuracy/attentive/a1 | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| reward/n3/eta0 | 0.5968 | 1.0000 | 0.6554 | 0.184 | 2.107 |
| reward/n3/eta0.05 | 0.5968 | 1.0000 | 0.6554 | 0.184 | 2.107 |
| reward/n3/eta0.15 | 0.5968 | 1.0000 | 0.6554 | 0.184 | 2.107 |
| reward/n3/eta0.5 | 0.5968 | 1.0000 | 0.6554 | 0.184 | 2.107 |
| reward/n3/eta1 | 0.5968 | 1.0000 | 0.6554 | 0.184 | 2.107 |
| reward/n10/eta0 | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| reward/n10/eta0.05 | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| reward/n10/eta0.15 | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| reward/n10/eta0.5 | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| reward/n10/eta1 | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| reward/n30/eta0 | 0.0000 | 1.0000 | 0.0000 | 2.672 | 3.336 |
| reward/n30/eta0.05 | 0.0000 | 1.0000 | 0.0000 | 2.672 | 3.336 |
| reward/n30/eta0.15 | 0.0000 | 1.0000 | 0.0000 | 2.672 | 3.336 |
| reward/n30/eta0.5 | 0.0000 | 1.0000 | 0.0000 | 2.672 | 3.336 |
| reward/n30/eta1 | 0.0000 | 1.0000 | 0.0000 | 2.672 | 3.336 |
| positions/n10-lazy/uniform | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| positions/n10-lazy/power_law | 0.2532 | 1.0000 | 0.3594 | 0.844 | 2.450 |
| positions/n10-lazy/whale | 0.1838 | 1.0000 | 0.2792 | 0.844 | 2.447 |
| positions/n10-attentive/uniform | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| positions/n10-attentive/power_law | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| positions/n10-attentive/whale | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| positions/n30-lazy/uniform | 0.0000 | 1.0000 | 0.0000 | 2.672 | 3.336 |
| positions/n30-lazy/power_law | 0.0000 | 1.0000 | 0.0002 | 2.672 | 3.336 |
| positions/n30-lazy/whale | 0.0002 | 1.0000 | 0.0014 | 2.672 | 3.336 |
| positions/n30-attentive/uniform | 0.0000 | 1.0000 | 0.0000 | 25.658 | 14.829 |
| positions/n30-attentive/power_law | 0.0000 | 1.0000 | 0.0000 | 25.658 | 14.829 |
| positions/n30-attentive/whale | 0.0000 | 1.0000 | 0.0000 | 25.658 | 14.829 |
| compensation/L5000-retail/fee0 | 0.7484 | 0.8790 | 0.8790 | 0.733 | 9.191 |
| compensation/L5000-retail/fee5 | 0.7486 | 0.8796 | 0.8796 | 0.734 | 9.197 |
| compensation/L5000-retail/fee15 | 0.4172 | 0.9912 | 0.4700 | 0.834 | 10.343 |
| compensation/L5000-retail/fee50 | 0.4166 | 0.9912 | 0.4682 | 0.834 | 10.343 |
| compensation/L5000-mixed/fee0 | 0.6690 | 0.9610 | 0.9610 | 0.791 | 10.082 |
| compensation/L5000-mixed/fee5 | 0.6690 | 0.9612 | 0.9612 | 0.791 | 10.084 |
| compensation/L5000-mixed/fee15 | 0.2918 | 1.0000 | 0.3916 | 0.841 | 10.446 |
| compensation/L5000-mixed/fee50 | 0.2876 | 1.0000 | 0.3842 | 0.841 | 10.446 |
| compensation/L5000-specialized/fee0 | 0.6204 | 0.9652 | 0.9652 | 0.800 | 10.143 |
| compensation/L5000-specialized/fee5 | 0.6204 | 0.9654 | 0.9654 | 0.800 | 10.145 |
| compensation/L5000-specialized/fee15 | 0.2524 | 1.0000 | 0.3584 | 0.844 | 10.450 |
| compensation/L5000-specialized/fee50 | 0.2500 | 1.0000 | 0.3530 | 0.844 | 10.449 |
| compensation/L50000-retail/fee0 | 0.1594 | 0.1614 | 0.1614 | 0.139 | 1.684 |
| compensation/L50000-retail/fee5 | 0.1594 | 0.1614 | 0.1614 | 0.139 | 1.684 |
| compensation/L50000-retail/fee15 | 0.1594 | 0.1614 | 0.1614 | 0.139 | 1.684 |
| compensation/L50000-retail/fee50 | 0.1460 | 0.2974 | 0.1468 | 0.257 | 3.103 |
| compensation/L50000-mixed/fee0 | 0.7282 | 0.8364 | 0.8364 | 0.695 | 8.740 |
| compensation/L50000-mixed/fee5 | 0.7284 | 0.8366 | 0.8366 | 0.695 | 8.742 |
| compensation/L50000-mixed/fee15 | 0.7284 | 0.8366 | 0.8366 | 0.695 | 8.742 |
| compensation/L50000-mixed/fee50 | 0.4174 | 0.9808 | 0.4630 | 0.827 | 10.234 |
| compensation/L50000-specialized/fee0 | 0.7012 | 0.9606 | 0.9606 | 0.790 | 10.069 |
| compensation/L50000-specialized/fee5 | 0.7012 | 0.9606 | 0.9606 | 0.790 | 10.069 |
| compensation/L50000-specialized/fee15 | 0.7012 | 0.9606 | 0.9606 | 0.790 | 10.069 |
| compensation/L50000-specialized/fee50 | 0.3296 | 1.0000 | 0.4260 | 0.842 | 10.446 |
| honest_griefing/a0.7/ratio0.001 | 0.1280 | 1.0000 | 0.0000 | 0.834 | 2.525 |
| honest_griefing/a0.7/ratio0.01 | 0.1280 | 1.0000 | 0.0000 | 0.834 | 2.525 |
| honest_griefing/a0.7/ratio0.1 | 0.0942 | 1.0000 | 0.0000 | 0.831 | 2.496 |
| honest_griefing/a0.7/ratio1 | 0.0096 | 1.0000 | 0.0000 | 0.841 | 2.429 |
| honest_griefing/a0.9/ratio0.001 | 0.0436 | 1.0000 | 0.0000 | 0.838 | 2.530 |
| honest_griefing/a0.9/ratio0.01 | 0.0436 | 1.0000 | 0.0000 | 0.838 | 2.530 |
| honest_griefing/a0.9/ratio0.1 | 0.0222 | 1.0000 | 0.0000 | 0.845 | 2.477 |
| honest_griefing/a0.9/ratio1 | 0.0000 | 1.0000 | 0.0000 | 0.844 | 2.422 |
| honest_griefing/a0.99/ratio0.001 | 0.0050 | 1.0000 | 0.0000 | 0.844 | 2.510 |
| honest_griefing/a0.99/ratio0.01 | 0.0030 | 1.0000 | 0.0000 | 0.844 | 2.476 |
| honest_griefing/a0.99/ratio0.1 | 0.0000 | 1.0000 | 0.0000 | 0.844 | 2.422 |
| honest_griefing/a0.99/ratio1 | 0.0000 | 1.0000 | 0.0000 | 0.844 | 2.422 |
| thin_attention/n3/multiplier0.1 | 0.6250 | 1.0000 | 0.6554 | 0.063 | 2.039 |
| thin_attention/n3/multiplier1 | 0.4256 | 1.0000 | 0.6554 | 0.516 | 2.318 |
| thin_attention/n3/multiplier5 | 0.0642 | 1.0000 | 0.1846 | 1.450 | 2.757 |
| thin_attention/n10/multiplier0.1 | 0.4636 | 1.0000 | 0.4852 | 0.086 | 2.049 |
| thin_attention/n10/multiplier1 | 0.3168 | 1.0000 | 0.4852 | 0.821 | 2.455 |
| thin_attention/n10/multiplier5 | 0.0000 | 1.0000 | 0.0000 | 3.290 | 3.645 |
| thin_attention/n30/multiplier0.1 | 0.4596 | 1.0000 | 0.5000 | 0.094 | 2.058 |
| thin_attention/n30/multiplier1 | 0.0000 | 1.0000 | 0.0000 | 0.916 | 2.458 |
| thin_attention/n30/multiplier5 | 0.0000 | 1.0000 | 0.0000 | 4.247 | 4.124 |
| challenge_access/retail/ratio0.01 | 0.0966 | 0.1618 | 0.1368 | 0.139 | 0.406 |
| challenge_access/retail/ratio0.1 | 0.1208 | 0.2982 | 0.1448 | 0.257 | 0.731 |
| challenge_access/retail/ratio0.5 | 0.1434 | 0.2982 | 0.1472 | 0.257 | 0.726 |
| challenge_access/retail/ratio1 | 0.1464 | 0.2982 | 0.1472 | 0.257 | 0.725 |
| challenge_access/mixed/ratio0.01 | 0.5042 | 0.8632 | 0.7340 | 0.729 | 2.163 |
| challenge_access/mixed/ratio0.1 | 0.3166 | 0.9808 | 0.4352 | 0.827 | 2.406 |
| challenge_access/mixed/ratio0.5 | 0.3804 | 0.9808 | 0.4656 | 0.827 | 2.397 |
| challenge_access/mixed/ratio1 | 0.4242 | 0.9808 | 0.4760 | 0.827 | 2.389 |
| selection/lazy-uniform/first_willing | 0.2814 | 1.0000 | 0.4122 | 0.844 | 2.456 |
| selection/lazy-uniform/worst_willing | 0.5824 | 1.0000 | 0.8526 | 0.848 | 2.495 |
| selection/lazy-whale/first_willing | 0.1838 | 1.0000 | 0.2792 | 0.844 | 2.447 |
| selection/lazy-whale/worst_willing | 0.5118 | 1.0000 | 0.9122 | 0.848 | 2.529 |
| selection/attentive-uniform/first_willing | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| selection/attentive-uniform/worst_willing | 0.0000 | 1.0000 | 0.0000 | 7.953 | 5.977 |
| selection/attentive-whale/first_willing | 0.0000 | 1.0000 | 0.0000 | 7.967 | 5.984 |
| selection/attentive-whale/worst_willing | 0.0000 | 1.0000 | 0.0000 | 7.953 | 5.977 |

## Scope and decision rules

The first willing proposer in an independent random priority order submits; a separately labeled worst-willing stress gives priority to fraud. Candidates choose truth, falsehood, or abstention from the same expected challenge rule used in execution. Inspection readiness is provisioned operational capacity, and each ready observer follows a positive incremental-EV filing policy. This experiment does not claim that this policy is the unique dynamic waiting equilibrium. The separate neutral-monitor inspection game tests endogenous participation and free-riding.

Free bond capital excludes already collateralized positions. Capital eligibility covers bond plus cash work costs. Opportunity cost reserves the maximum proposer lock (window plus adjudication delay); challenger opportunity cost covers adjudication. A failed challenge goes entirely to protocol reserve; an overturned proposer funds the declared challenger reward and protocol remainder. The proposer success fee is paid even when an erroneous outcome survives, as the protocol cannot observe objective truth directly.

Except in the explicit compensation and honest-griefing treatments, the success fee is F=max(5, proposer work + conservative lock opportunity cost +1). Thus the bond/window comparisons include this declared service-funding rule; they do not silently hold an inadequate fixed fee while counting resulting deferral as integrity. The compensation family separately tests inadequate versus adequate service payment.

All candidates' abstention benchmark is zero incremental service payoff relative to eventual truthful fallback; a no-submission episode is recorded as deferred, without fabricating a correct immediate finalization. Outcome-neutral payment for legitimate blueprint cancellations belongs to the separate executable-workflow model. Composition-blocked attacks and missing-evidence cancellations are likewise not relabeled as economic deterrence in this game.

Each uniform/power-law/whale allocation puts exclusive binary claims into two nonempty groups and normalizes each outcome column to the same pool. This makes signed gains sum to zero. Payout misallocation is a redistribution measure, not aggregate welfare destruction; real work and capital opportunity cost are reported separately. Numerical rates are synthetic comparative statics, not empirically calibrated deployment defaults.
