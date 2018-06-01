#  Copyright 2018 David Huberdeau & Peter Kok
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""Inverted Encoding Model (IEM)

    Method to decode and reconstruct features from data.

    The implementation is roughly based on the following publications:

    [Kok2013] "1.Kok, P., Brouwer, G. J., Gerven, M. A. J. van &
    Lange, F. P. de. Prior Expectations Bias Sensory Representations
    in Visual Cortex. J. Neurosci. 33, 16275–16284 (2013).

    [Bouwer2009] "1.Brouwer, G. J. & Heeger, D. J.
    Decoding and Reconstructing Color from Responses in Human Visual
    Cortex. J. Neurosci. 29, 13992–14003 (2009).
"""

# Authors: David Huberdeau (Yale University) &
# Peter Kok (Yale University), 2018

import logging
import numpy as np
from sklearn import linear_model
from sklearn.base import BaseEstimator
import math

__all__ = [
    "InvertedEncoding"
]

logger = logging.getLogger(__name__)


class InvertedEncoding(BaseEstimator):
    """Basis function-based reconstruction method

    Inverted encoding models (alternatively known as forward
    models) are used to reconstruct a feature, e.g. color of
    a stimulus, from patterns across voxels in functional
    data. The model uses n_channels number of idealized
    basis functions and assumes that the transformation from
    stimulus feature (e.g. color) to basis function is one-
    to-one and invertible. The response of a voxel is
    expressed as the weighted sum of basis functions.
    In this implementation, basis functions were half-wave
    sinusoids raised to an even power (in this case, 6).

    To use this model, estimate the weights of the basis
    functions separately for each voxel via linear
    regression (using fit()). Then, as part of predict(),
    compute channel outputs for new functional data (done
    by _predict_channel_responses()), and associate those
    responses to a feature type. Score() computes a measure
    of the error of the prediction based on known ground
    truth.

    This implementation assumes a circular (or half-
    circular) feature domain. Future implementations might
    generalize the feature input space, and increase the
    possible dimensionality.

    Parameters
    ----------
    n_channels: int, default 5, number of channels
        The number of channels, or basis functions, to be used
        in the inverted encoding model

    range_start: double, default 0, beginning of range of
        independent variable (usually degrees)

    range_stop: double, default 180, end of range of
        independent variable (usually degrees)


    Attributes
    ----------
    C_: [n_channels, channel density] NumPy 2D array
        matrix defining channel values

    C_D_: [n_channels, channel density] NumPy 2D array
        matrix defining channel independent variable (usually
        in degrees)

    W_: sklearn.linear_model model containing weight matrix that
        relates estimated channel responses to response amplitude
        data
    """
    def __init__(self, n_channels=5, range_start=0, range_stop=180):

        self.n_channels = n_channels  # default = 5
        self.range_start = range_start  # in degrees, 0 - 360, def=0
        self.range_stop = range_stop  # in degrees, 0 - 360, def=180

    def fit(self, X, y):
        """Use data and feature variable labels to fit an IEM

        Parameters
        ----------
        X: numpy matrix of voxel activation data. [observations, voxels]
            Should contain the beta values for each observation or
            trial and each voxel of training data.
        y: numpy array of response variable. [observations]
            Should contain the feature for each observation in X.

        Returns
        -------
        iem: self.
        """
        # Check that there are channels specified
        if self.n_channels < 2:
            raise ValueError("Insufficient channels.")
        # Check that there is enough data.. should be more
        # samples than voxels (i.e. X should be tall)
        shape_data = np.shape(X)
        shape_labels = np.shape(y)
        if len(shape_data) < 2:
            raise ValueError("Not enough data")
        else:
            if np.size(X, 0) <= np.size(X, 1):
                raise ValueError("Data Matrix ill-conditioned")
            if shape_data[0] != shape_labels[0]:
                raise ValueError(
                    "Mismatched data samples and label samples")

        self.C_, self.C_D_ = self._define_channels()
        n_train = len(y)
        F = np.empty((n_train, self.n_channels))
        for i_tr in range(n_train):
            # Find channel activation for this orientation
            k_min = np.argmin((y[i_tr] - self.C_D_)**2)
            F[i_tr, :] = self.C_[:, k_min]
        clf = linear_model.LinearRegression(fit_intercept=False,
                                            normalize=False)
        clf.fit(F, X)
        self.W_ = clf
        return self

    def predict(self, X):
        """Use test data to predict feature

        Parameters
        ----------
            X: numpy matrix of voxel activation from test trials
            [observations, voxels]. Used to predict feature
            associated with the given observation.

        Returns
        -------
            pred_dir: numpy array of estimated feature values.
        """
        # Check that there is enough data.. should be more
        # samples than voxels (i.e. X should be tall)
        shape_data = np.shape(X)
        if len(shape_data) < 2:
            raise ValueError("Not enough data")
        else:
            if np.size(X, 0) <= np.size(X, 1):
                raise ValueError("Data Matrix ill-conditioned")
        pred_response = self._predict_directions(X)
        pred_indx = np.argmax(pred_response, axis=1)
        pred_dir = self.C_D_[pred_indx]
        return pred_dir

    def score(self, X, y):
        """Calculate error measure of prediction.

        Parameters
        ----------
            X: numpy matrix of voxel activation from new data
                [observations,voxels]
            y: numpy array of responses. [observations]

        Returns
        -------
            rss: residual sum of squares of predicted
                features compared to to actual features.
        """
        pred_dir = self.predict(X)
        u = ((y - pred_dir)**2).sum()
        v = ((y - np.mean(y))**2).sum()
        rss = (1 - u/v)
        return rss

    def get_params(self, deep=True):
        """Returns model parameters.

        Parameters
        ----------
        deep: boolean. default true.
            if true, returns params of sub-objects

        Returns
        -------
        params: parameter of this object
        """
        return{"n_channels": self.n_channels,
               "range_start": self.range_start,
               "range_stop": self.range_stop}

    def set_params(self, **parameters):
        """Sets model parameters after initialization.

        Parameters
        ----------
            params: structure with parameters and change values

        Returns
        -------
            self.
        """
        for parameter, value in parameters.items():
            setattr(self, parameter, value)
        return self

    def _define_channels(self):
        """Define basis functions (aka channels).

        Parameters
        ----------
            self.

        Returns
        -------
            channels: numpy matrix of basis functions.
                    [n_channels, function resolution].
            channel_domain: numpy array of domain values.
        """
        channel_exp = 6
        channel_density = 180
        shifts = np.linspace(0,
                             math.pi - math.pi/self.n_channels,
                             self.n_channels)

        channel_domain = np.linspace(self.range_start,
                                     self.range_stop,
                                     channel_density)

        channels = np.zeros((self.n_channels, channel_density))
        for i in range(self.n_channels):
            channels[i, :] = np.cos(np.linspace(0, math.pi, channel_density)
                                    - shifts[i]) ** channel_exp
        # Check that channels provide sufficient coverage
        ch_sum_range = np.max(np.sum(channels, 0)) - min(np.sum(channels, 0))
        if ch_sum_range > np.deg2rad(self.range_stop - self.range_start)*0.1:
            # if range of channel sum > 10% channel domain size
            raise ValueError("Insufficient channel coverage.")
        return channels, channel_domain

    def _predict_channel_responses(self, X):
        """Computes predicted basis function values from data

        Parameters
        ----------
            X: numpy data matrix. [observations, voxels]

        Returns
        -------
            channel_response: numpy matrix of channel responses
        """
        clf = linear_model.LinearRegression(fit_intercept=False,
                                            normalize=False)
        clf.fit(self.W_.coef_, X.transpose())
        channel_response = clf.coef_
        return channel_response

    def _predict_directions(self, X):
        """Predicts feature value (direction) from data

        Parameters
         ---------
            X: numpy matrix of data. [observations, voxels]

        Returns
        -------
            pred_response: predict response from all channels. Used
                        to predict feature (direction).
        """
        pred_response = self._predict_channel_responses(X).dot(self.C_)
        return pred_response
