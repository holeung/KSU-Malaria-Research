from src.data.data_abstract import DataAbstract
from src.data.data_non_linear import DataNonLinear
from sklearn.preprocessing import MinMaxScaler
import pandas as pd
from numpy import squeeze
from streamml.src.streamline.transformation.flow.TransformationStream import TransformationStream

class DataTransformation(DataAbstract):
    def __init__(self):
        DataAbstract.__init__(self)
        self.cache = True

    @staticmethod
    def clean_data(data):
        """
        Seperate into x and y data
        """
        # Convert string data to nan
        data = data.apply(pd.to_numeric, errors='coerce')
        data = data.loc[:, (data.std() > 0).values]
        # Split x, y
        y_data = data.pop("IC50")
        x_data = data.copy().fillna(0)
        return x_data, y_data

    @staticmethod
    def engineer_features(X, y_data=None):
        """
        Example implementation steps:
          * Perform feature engineering (use additional methods as needed, or static file)
          * Check for unexpected values
        :param x_data:
        :return: return x_data with new features
        """
        # Trasnform
        formed = TransformationStream(X).flow(["scale",
                                                "normalize",
                                                "pca",
                                                "kmeans"], 
                                               params={"pca__percent_variance":0.95
                                                       "kmeans__n_clusters":2})
        return formed

    @staticmethod
    def test_train_split(x_data, y_data):
        """
          * Scale using MinMaxScaler
          * Split train/test based on missing target variables
        :param x_data:
        :param y_data:
        :return: x_train, x_test, y_train
        """
        y_scaler = MinMaxScaler()
        x_scaler = MinMaxScaler()

        test_index = y_data.isnull()
        x_train = x_data.loc[~test_index].copy()
        y_train = y_data.loc[~test_index].copy()
        x_test = x_data.loc[test_index].copy()

        x_train.loc[:, :] = x_scaler.fit_transform(x_train)
        x_test.loc[:, :] = x_scaler.transform(x_test)
        y_train.loc[:] = squeeze(y_scaler.fit_transform(y_train.values.reshape(-1, 1)))
        return x_train, x_test, y_train, y_scaler