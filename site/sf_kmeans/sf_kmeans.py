"""
K-Means algorithm implementation using Mahalanobis distances.
The algorithm is structured to maximize the likelihood of a model that uses a multivariate normal distribution
 for each cluster.

Authors: Nevena Golubovic, Angad Gill
"""

import numpy as np
from numpy.linalg import LinAlgError
from scipy.spatial.distance import cdist
from sklearn.utils.extmath import squared_norm
from sklearn.cluster import k_means_


class SF_KMeans(object):
    def __init__(self, n_clusters=2, max_iter=300, tol=0.0001, verbose=0, n_init=10,
                 metric='mahalanobis', use_rss=False, covar_type='full', covar_tied=False,
                 min_members='auto', warm_start=False, **kwargs):
        self.n_clusters = n_clusters
        self.max_iter = max_iter
        self.tol = tol
        self.verbose = verbose
        self.n_init = n_init  # num. of times to run k-means
        if metric not in ['mahalanobis', 'euclidean']:
            raise ValueError('Metric "{}" not valid. Must be "mahalanobis" or "euclidean".'.format(metric))
        self.metric = metric
        self.use_rss = use_rss
        self.labels_ = None
        self.cluster_centers_ = None
        self._inv_covar_matrices = None  # shape: (n_clusters, dim, dim)
        self._global_covar_matrices = None # shape: (n_clusters, dim, dim)
        if covar_type not in ['full', 'diag', 'spher', 'global']:
            raise ValueError('Covariance type "{}" not valid. Must be "full", "diag", "spher", "global".'.format(covar_type))
        self.covar_type = covar_type
        self.covar_tied = covar_tied  # Only used with full, diag, spher covar_types
        self.warm_start = warm_start  # If True, cluster centers are not re-initialized each time fit is called
        self.min_members = min_members
        self.all_labels_ = []
        self.best_inertia_ = None
        self.inertias_ = []
        self.log_likelihoods_ = []

    def fit(self, data):
        """
        Run K-Means on data n_init times.

        Parameters
        ----------
        data: numpy array

        Returns
        -------
        No value is returned.
        Function sets the following two object params:
            self.labels_
            self.cluster_centers_
        """
        data = np.array(data)
        labels, cluster_centers = [], []
        for i in range(self.n_init):
            if not self.warm_start:
                self.cluster_centers_ = None
                self._global_covar_matrices = None
                self._inv_covar_matrices = None
            self._fit(data)
            labels += [self.labels_]
            cluster_centers += [self.cluster_centers_]
            self.inertias_ += [self._inertia(data)]
            self.log_likelihoods_ += [self.log_likelihood(data)]
        best_idx = np.argmin(self.inertias_)
        self.labels_ = labels[best_idx]
        self.all_labels_ = labels
        self.best_log_likelihood_ = self.log_likelihoods_[best_idx]
        self.best_inertia_ = self.inertias_[best_idx]
        self.cluster_centers_ = cluster_centers[best_idx]
        if self.verbose == 1:
            print('fit: n_clusters: {}, label bin count: {}'.format(self.n_clusters, np.bincount(self.labels_, minlength=self.n_clusters)))


    def _fit(self, data):
        """
        Run K-Means on data once.

        Parameters
        ----------
        data: numpy array

        Returns
        -------
        No value is returned.
        Function sets the following two object params:
            self.labels_
            self.cluster_centers_
        """
        if self.min_members == 'auto':
            self._min_members = data.shape[1]
        else:
            self._min_members = self.min_members

        data = np.array(data)
        distances = np.zeros((data.shape[0], self.n_clusters))
        distances.fill(float('inf'))

        """ Initial assignment """
        if self.cluster_centers_ is None:
            self.cluster_centers_ = k_means_._init_centroids(data, self.n_clusters, 'k-means++')
            for k in range(self.n_clusters):
                k_dist = cdist(data, np.array([self.cluster_centers_[k]]), metric='euclidean')
                distances[:, k] = k_dist.reshape((data.shape[0],))
            self.labels_ = np.argmin(distances, axis=1)
            self.cluster_centers_ = self._compute_cluster_centers(data)

        old_cluster_centers_ = self.cluster_centers_

        for i in range(self.max_iter):
            distances.fill(float('inf'))

            if self.verbose == 2:
                print('\riteration: {}/{}'.format(i + 1, self.max_iter))

            """ Compute covariance matrices and inverse covariance matrices """

            covar_matrices = self.covariances(self.labels_, cluster_centers=self.cluster_centers_, data=data)
            # TODO: make this go faster for tied matrices
            self._inv_covar_matrices = self._matrix_inverses(covar_matrices)

            nks = np.bincount(self.labels_, minlength=self.n_clusters)  # number of points in each cluster

            for k, nk in enumerate(nks):
                k_dist = cdist(data, np.array([self.cluster_centers_[k]]), metric=self.metric, VI=self._inv_covar_matrices[k])
                k_dist[np.isnan(k_dist)] = float('inf')  #  to deal with nans in cdist return
                distances[:, k] = k_dist.reshape((data.shape[0],))

            labels = np.argmin(distances, axis=1)
            nks = np.bincount(labels, minlength=self.n_clusters)  # number of points in each cluster

            if 0 in nks:  # at least one empty cluster
                # move empty clusters to points farthest away from its cluster center
                empty_clusters_idx = np.argwhere(nks == 0).flatten()
                max_distances = np.min(distances, axis=1)  # distance of each point from its cluster center
                farthest_point_idx = list(np.argsort(max_distances))

                for c_idx in empty_clusters_idx:
                    idx = farthest_point_idx.pop()
                    single_point_clusters_idx = np.argwhere(nks == 1).flatten()
                    while labels[idx] in single_point_clusters_idx:
                        # find a point that is not in single point cluster
                        idx = farthest_point_idx.pop()
                    labels[idx] = c_idx
                    nks = np.bincount(labels, minlength=self.n_clusters)

            self.labels_ = labels
            self.cluster_centers_ = self._compute_cluster_centers(data)

            center_shift_total = squared_norm(old_cluster_centers_ - self.cluster_centers_)
            if self.verbose == 2:
                print('center_shift_total: {:0.6f}'.format(center_shift_total))
            if center_shift_total <= self.tol:
                if self.verbose >= 4:
                    print('Converged after {} iterations.'.format(i + 1))
                break
            old_cluster_centers_ = self.cluster_centers_
        # self.labels_ = self.reset_labels(self.labels_)
        # self.cluster_centers_ = self._compute_cluster_centers(data)

    @staticmethod
    def reset_labels(labels):
        """ Resets label numbers so that they are sequential. For example, [0, 0, 3, 3, 1, 1] --> [0, 0, 1, 1, 2, 2] """
        _, sorted_unique_indices = np.unique(labels, return_index=True)
        unique_labels = [labels[i] for i in sorted(sorted_unique_indices)]  # order preserved
        new_label_map = dict([(l, i) for i, l in enumerate(unique_labels)])
        new_labels = [new_label_map[l] for l in labels]
        return np.array(new_labels)

    def _initial_farthest_traversal(self, data, seed=None):
        """ Find the initial set of cluster centers using Farthest Traversal strategy """
        # Pick first at random
        np.random.seed(seed)
        centers = data[np.random.randint(low=0, high=data.shape[0], size=1)]
        for _ in range(self.n_clusters - 1):
            dist = cdist(data, centers)
            dist = dist.sum(axis=1)
            assert dist.shape[0] == data.shape[0]  # making sure that axis=1 is correct
            # point with max. dist from all centers becomes a new center
            centers = np.append(centers, [data[np.argmax(dist)]], axis=0)
        return centers

    def _inertia(self, data):
        """ Sum of distances of all data points from their cluster centers """
        distances = np.zeros((data.shape[0], self.n_clusters))
        covar_matrices = self.covariances(self.labels_, cluster_centers=self.cluster_centers_, data=data)
        self._inv_covar_matrices = self._matrix_inverses(covar_matrices)
        for k in range(self.n_clusters):
            k_dist = cdist(data, np.array([self.cluster_centers_[k]]), metric=self.metric,
                           VI=self._inv_covar_matrices[k])
            k_dist = k_dist.reshape((data.shape[0],))
            distances[:, k] = k_dist
        distances = distances.min(axis=1)
        assert distances.shape[0] == data.shape[0]
        return distances.sum()

    def _rss(self, data):
        """ Residual Sum of Square distances of all data points from their cluster centers """
        if self.metric == 'euclidean':
            distances = cdist(data, self.cluster_centers_, metric='euclidean')
        elif self.metric == 'mahalanobis':
            #covar_matrix = self.covariance(labels=self.labels_, cluster_centers=self.cluster_centers_, data=data)
            covar_matrices = self.covariances(self.labels_,
                                            cluster_centers=self.cluster_centers_, data=data)[0]
            self._inv_covar_matrices = self._matrix_inverses(covar_matrices)
            distances = cdist(data, self.cluster_centers_, metric='mahalanobis', VI=self._inv_covar_matrices)
        distances = distances.min(axis=1)
        distances = distances ** 2
        assert distances.shape[0] == data.shape[0]
        return distances.sum()

    def _compute_cluster_centers(self, data):
        """
        Computes the center of each cluster using self.labels_

        Parameters
        ----------
        data: input data

        Returns
        -------
        cluster_centers: numpy ndarray with shape: (self.n_clusters, data.shape[1])

        """
        cluster_centers = []
        for k in range(self.n_clusters):
            datapoints_in_k = data[self.labels_ == k]
            if self.metric == 'euclidean':
                cluster_centers += [datapoints_in_k.mean(axis=0)]
            elif self.metric == 'mahalanobis':
                # cluster_centers += [self._center_mahalanobis(datapoints_in_k)]
                cluster_centers += [datapoints_in_k.mean(axis=0)]
        cluster_centers = np.array(cluster_centers)
        assert cluster_centers.shape == (self.n_clusters, data.shape[1])
        return cluster_centers

    def _center_mahalanobis(self, data):
        """
        Finds a point that is in the center of the data using Mahalanobis distance.

        Parameters
        ----------
        data: input data as numpy array

        Returns
        -------
        mean: numpy array
        """
        distances = cdist(data, data, metric='mahalanobis', VI=self._inv_covar_matrices)
        sum_distances = np.sum(distances, axis=0)
        center_idx = np.argmin(sum_distances)
        return data[center_idx]

    def _matrix_inverse(self, matrix):
        """
        Computes inverse of a matrix.
        """
        matrix = np.array(matrix)
        n_features = matrix.shape[0]
        rank = np.linalg.matrix_rank(matrix)

        if rank == n_features:
            return np.linalg.inv(matrix)
        else:
            # Matrix is not full rank, so use Hadi's technique to compute inverse
            # Reference: Ali S. Hadi (1992) "Identifying Multiple Outliers in Multivariate Data" eg. 2.3, 2.4
            eigenValues, eigenVectors = np.linalg.eig(matrix)
            eigenValues = np.abs(eigenValues)  # to deal with -0 values
            idx = eigenValues.argsort()[::-1]
            eigenValues = eigenValues[idx]
            eigenVectors = eigenVectors[:, idx]

            s = eigenValues[eigenValues != 0].min()
            w = [1 / max(e, s) for e in eigenValues]
            W = w * np.eye(n_features)

            return eigenVectors.dot(W).dot(eigenVectors.T)

    def _matrix_inverses(self, matrix_v):
        """
        Computes inverse of matrices.


        Parameters
        ----------
        matrix_v: list of matrices

        Returns
        -------
        matrix inverse: list of inverted matrices. type: list(numpy array)
        """
        if self.covar_type == 'global':
            if self._inv_covar_matrices is None:
                self._inv_covar_matrices = [self._matrix_inverse(matrix_v[0])] * self.n_clusters
            return self._inv_covar_matrices

        if self.covar_tied:
            return [self._matrix_inverse(matrix_v[0])]*self.n_clusters
        else:
            return [self._matrix_inverse(c) for c in matrix_v]

    @staticmethod
    def labels_to_resp(labels, n_clusters):
        labels = np.array(labels)
        assert len(labels.shape) == 1
        resp = np.zeros((labels.shape[0], n_clusters))
        resp[np.arange(labels.shape[0]), labels] = 1
        return resp

    # TODO: Delete cluster_centers from args
    def covariances(self, labels, cluster_centers, data):
        """
        Computes covariance based on  Kevin P. Murphy. "Fitting a Conditional Linear Gaussian Distribution" (2003).

        Parameters
        ----------
        labels: list of cluster labels of each data point. Shape: (number of data points)
        cluster_centers: numpy array of all cluster centers. Shape: (number of clusters, dimensions of data set)
        data: numpy array of input data. Shape:(number of data points, dimensions of data set)

        Returns:
        -------
        covariance matrix. Shape: (number of clusters, dimensions of data set, dimensions of data set)
        """
        n_clusters = self.n_clusters
        n_features = data.shape[1]
        covariances_v = np.array([np.eye(n_features)]*n_clusters)
        nks = np.bincount(labels, minlength=self.n_clusters)

        if self.covar_type == 'global':
            if self._global_covar_matrices is None:
                if data.shape[1] == 1:
                    covar = np.array([[np.cov(data.T)]])
                else:
                    covar = np.cov(data.T)
                assert covar.shape == (data.shape[1], data.shape[1])
                self._global_covar_matrices = [covar] * self.n_clusters
            return self._global_covar_matrices

        elif self.covar_type == 'full' and not self.covar_tied:
            for k in range(n_clusters):
                if nks[k] > self._min_members:
                    data_k = data[labels==k]
                    covar = np.cov(data_k.T, bias=True)
                    covariances_v[k] = covar

        elif self.covar_type == 'full' and self.covar_tied:
            covar = np.zeros((n_features, n_features))
            for k in range(n_clusters):
                if nks[k] > self._min_members:
                    data_k = data[labels==k]
                    covar += np.cov(data_k.T, bias=True)
            covar /= n_clusters
            covariances_v[:] = covar

        if self.covar_type == 'diag' and not self.covar_tied:
            for k in range(n_clusters):
                if nks[k] > self._min_members:
                    data_k = data[labels==k]
                    covar = np.cov(data_k.T, bias=True)
                    covar *= np.eye(n_features)  # zero out non-diagonal elements
                    covariances_v[k] = covar

        elif self.covar_type == 'diag' and self.covar_tied:
            covar = np.zeros((n_features, n_features))
            for k in range(n_clusters):
                if nks[k] > self._min_members:
                    data_k = data[labels==k]
                    covar += np.cov(data_k.T, bias=True)
            covar /= n_clusters
            covar *= np.eye(n_features)  # zero out non-diagonal elements
            covariances_v[:] = covar

        if self.covar_type == 'spher' and not self.covar_tied:
            for k in range(n_clusters):
                if nks[k] > self._min_members:
                    data_k = data[labels==k]
                    covar = np.var(data_k, axis=0)  # var of each feature
                    covar = np.mean(covar)
                    covar *= np.eye(n_features)
                    covariances_v[k] = covar

        elif self.covar_type == 'spher' and self.covar_tied:
            covar = np.zeros(n_features)
            for k in range(n_clusters):
                if nks[k] > self._min_members:
                    data_k = data[labels==k]
                    covar += np.var(data_k, axis=0)  # var of each feature
            covar /= n_clusters
            covar = np.mean(covar)
            covar *= np.eye(n_features)  # zero out non-diagonal elements
            covariances_v[:] = covar

        # It is possible for the determinant of the covariance matrix to be zero
        # when there are less than n_features independent points in the dataset
        # In this case, set the covariance matrix to the identity matrix to force the use
        # of euclidean distance.
        for idx, c in enumerate(covariances_v):
            if np.linalg.det(c) <= 0:
                if self.verbose == 1:
                    print("det is {}, matrix is {}, nk:{}".format(np.linalg.det(c), c, np.bincount(labels, minlength=n_clusters)[idx]))
                covariances_v[idx] = np.eye(n_features)

        return covariances_v

    @staticmethod
    def covariance(labels, cluster_centers, data):
        """
        Computes covariance where the mean is cluster-specific.

        Parameters
        ----------
        labels: list of labels of each data point. Shape: (number of data points)
        cluster_centers: numpy array of all cluster centers. Shape: (number of clusters, dimensions of data set)
        data: numpy array of input data. Shape:(number of data points, dimensions of data set)

        Returns
        -------
        covariance matrix. Shape: (dimensions of data set, dimensions of data set)
        """
        covar = 0
        data = np.array(data)
        labels = np.array(labels)
        cluster_centers = np.array(cluster_centers)
        # d is a row in the data, i is its index
        for i, d in enumerate(data):
            label = labels[i]
            mean = cluster_centers[label]
            var = d - mean
            covar += np.outer(var, var)
        covar = covar / float(data.shape[0])
        assert covar.shape == (data.shape[1], data.shape[1])
        return covar

    @staticmethod
    def cluster_local_covariance_vector(data, labels):
        covar_v = []
        data = np.array(data)
        labels = np.array(labels)
        for k in np.unique(labels):
            tmp = data[labels==k]
            if data.shape[1] == 1:
                covar = np.array([[np.cov(tmp.T)]])
            else:
                covar = np.cov(tmp.T)
            assert covar.shape == (tmp.shape[1], tmp.shape[1])
            covar_v.append(covar)
        return covar_v

    def log_likelihood(self, data):
        nks = np.bincount(self.labels_, minlength=self.n_clusters)  # number of points in each cluster
        n, d = data.shape
        log_likelihood = 0
        covar_matrices = self.covariances(self.labels_, cluster_centers=self.cluster_centers_, data=data)
        covar_matrix_det_v = np.linalg.det(covar_matrices)
        self._inv_covar_matrices = self._matrix_inverses(covar_matrices)
        for k, nk in enumerate(nks):
            if self.verbose == 1:
                print('log_likelihood: covar_matrix_det = {}'.format(covar_matrix_det_v[k]))
            term_1 = nk * (np.log(float(nk)/n) - 0.5 * d * np.log(2*np.pi) - 0.5 * np.log(abs(covar_matrix_det_v[k])))
            cdist_result = cdist(data[self.labels_ == k], np.array([self.cluster_centers_[k]]), metric='mahalanobis', VI=self._inv_covar_matrices[k])
            cdist_no_nan = cdist_result[~np.isnan(cdist_result)]  #  to deal with nans returned by cdist
            term_2 = -0.5 * (np.sum(cdist_no_nan))
            k_sum = term_1 + term_2
            log_likelihood += k_sum
        if np.isnan(log_likelihood) or log_likelihood == float('inf'):
            raise Exception('ll is nan or inf')
        return log_likelihood

    def free_parameters(self, data):
        """
        Compute free parameters for the model fit using K-Means
        """
        K = np.unique(self.labels_).shape[0]  # number of clusters
        n, d = data.shape
        r = (K - 1) + (K * d)
        if self.metric == 'euclidean':
            r += 1  # one parameter for variance
        elif self.metric == 'mahalanobis':
            if self.covar_type == 'full' and self.covar_tied:
                r += (d * (d + 1) * 0.5)  # half of the elements (including diagonal) in the matrix
            if self.covar_type == 'full' and not self.covar_tied:
                r += (d * (d + 1) * 0.5 * K)  # half of the elements (including diagonal) in the matrix
            if self.covar_type == 'diag' and self.covar_tied:
                r += d  # diagonal elements of the matrix
            if self.covar_type == 'diag' and not self.covar_tied:
                r += (d * K)  # diagonal elements of the matrix
            if self.covar_type == 'spher' and self.covar_tied:
                r += 1  # all diagonal elements are equal
            if self.covar_type == 'spher' and not self.covar_tied:
                r += K  # all diagonal elements are equal
        return r

    def bic(self, data):
        """
        Computes the BIC score for a model fit using K-Means.

        BIC = (max log likelihood) -  (free parameters * log (size of dataset) / 2)

        Parameters
        ----------
        data: input data

        Returns
        -------
        BIC score
        """
        data = np.array(data)
        n, d = data.shape
        penalty = 0.5 + self.free_parameters(data) * np.log(n)
        if self.use_rss:
            rss = self._rss(data)
            bic = n * np.log(rss / float(n)) - penalty
            if self.verbose == 1:
                print('rss: {:0.4f}, penalty:{:0.4f}, bic:{:0.4f}'.format(rss, penalty, bic))
        else:
            log_likelihood = self.log_likelihood(data)
            bic = log_likelihood - penalty
            if self.verbose == 1:
                print('log_likelihood: {:0.4f}, penalty:{:0.4f}, bic:{:0.4f}'.format(log_likelihood, penalty, bic))
        return bic

    def aic(self, data):
        """
        Computes AIC score for a model fit using K-Means.

        AIC = (max log likelihood) - (free parameters)

        Parameters
        ----------
        data: input data

        Returns
        -------
        AIC score
        """
        data = np.array(data)
        n, d = data.shape
        penalty = 0.5 + self.free_parameters(data)
        if self.use_rss:
            rss = self._rss(data)
            aic = n * np.log(rss / float(n)) - penalty
            if self.verbose == 1:
                print('rss: {:0.4f}, penalty:{:0.4f}, aic:{:0.4f}'.format(rss, penalty, aic))
        else:
            log_likelihood = self.log_likelihood(data)
            aic = log_likelihood - penalty
        if self.verbose == 1:
            print('log_likelihood: {:0.4f}, penalty:{:0.4f}, aic:{:0.4f}'.format(log_likelihood, penalty, aic))
        return aic
