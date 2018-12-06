import numpy as np
from sklearn import linear_model

from dowhy.causal_estimator import CausalEstimate
from dowhy.causal_estimator import CausalEstimator


class PropensityScoreWeightingEstimator(CausalEstimator):
    """ Estimate effect of treatment by stratifying the data into bins with
    identical common causes.

    Straightforward application of the back-door criterion.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.debug("Back-door variables used:" +
                          ",".join(self._target_estimand.backdoor_variables))
        self._observed_common_causes_names = self._target_estimand.backdoor_variables
        self._observed_common_causes = self._data[self._observed_common_causes_names]
        self.logger.info("INFO: Using Propensity Score Weighting Estimator")
        self.symbolic_estimator = self.construct_symbolic_estimator(self._target_estimand)
        self.logger.info(self.symbolic_estimator)
        self.weighting_scheme = 'ips_weight'  # 'itps_weight' 'ips_weight' 'nips_weight'
        self.min_ps_score = 0.05
        self.max_ps_score = 0.95

    def _estimate_effect(self):
        psmodel = linear_model.LinearRegression()
        psmodel.fit(self._observed_common_causes, self._treatment)
        self._data['ps'] = psmodel.predict(self._observed_common_causes)
        self._data['ps'] = np.minimum(self.max_ps_score, self._data['ps'])
        self._data['ps'] = np.maximum(self.min_ps_score, self._data['ps'])

        # trim propensity score weights

        # ips ==> (isTreated(y)/ps(y)) + ((1-isTreated(y))/(1-ps(y)))
        # nips ==> ips / (sum of ips over all units)
        # icps ==> ps(y)/(1-ps(y)) / (sum of (ps(y)/(1-ps(y))) over all control units)
        # itps ==> ps(y)/(1-ps(y)) / (sum of (ps(y)/(1-ps(y))) over all treatment units)
        ipst_sum = sum(self._data[self._treatment_name] / self._data['ps'])
        ipsc_sum = sum((1 - self._data[self._treatment_name]) / (1-self._data['ps']))
        self._data['ips_weight'] = (
            self._data[self._treatment_name] / self._data['ps'] / ipst_sum +
            (1 - self._data[self._treatment_name]) / (1 - self._data['ps']) / ipsc_sum
        )

        ips_sum = self._data['ips_weight'].sum()
        self._data['nips_weight'] = self._data['ips_weight'] / ips_sum

        self._data['ips2'] = self._data['ps'] / (1 - self._data['ps'])
        treated_ips_sum = (self._data['ips2'] * self._data[self._treatment_name]).sum()
        control_ips_sum = (self._data['ips2'] * (1 - self._data[self._treatment_name])).sum()

        self._data['itps_weight'] = self._data['ips2'] / treated_ips_sum
        self._data['icps_weight'] = self._data['ips2'] / control_ips_sum

        self._data['d_y'] = (
            self._data[self.weighting_scheme] *
            self._data[self._treatment_name] *
            self._data[self._outcome_name]
        )
        self._data['dbar_y'] = (
            self._data[self.weighting_scheme] *
            (1 - self._data[self._treatment_name]) *
            self._data[self._outcome_name]
        )

        ate = self._data['d_y'].sum() - self._data['dbar_y'].sum()

        # TODO - how can we add additional information into the returned estimate?
        estimate = CausalEstimate(estimate=ate,
                                  target_estimand=self._target_estimand,
                                  realized_estimand_expr=self.symbolic_estimator)
        return estimate

    def construct_symbolic_estimator(self, estimand):
        expr = "b: " + estimand.outcome_variable + "~"
        # TODO -- fix: we are actually conditioning on positive treatment (d=1)
        var_list = [estimand.treatment_variable, ] + estimand.backdoor_variables
        expr += "+".join(var_list)
        return expr
