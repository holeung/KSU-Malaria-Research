from sklearn.svm import SVR
import pickle
from src.models.model_abstract import ModelAbstract
from src.data.data_interactions import DataInteractions

"""
Template for model classes in the KSU project.
TODO's
  * Copy into new file
  * Rename class
  * Implement TODO's below
"""


class ModelSupportVectorRegressor(ModelAbstract):

    def __init__(self):
        ModelAbstract.__init__(self)
        self.data_object = DataTransformation()
        self.selected_features = []

    @staticmethod
    def select_features(x_data):
        """
        Example workflow
        * Select columns
        * Return set or list of column names
        :param x_data: full datasett
        :return:
        """
        topsis_features = pickle.load(open('../data/source_data/topsis_features.pickle', 'rw'))
        # Import columns from my analysis
        return topsis_features

    @staticmethod
    def choose_model(x_train, y_train):
        """
        Example workflow
          * Tune model parameters
        Return model (doesn't have to be trained)
        :param x_train:
        :param y_train:
        :return: sklearn model
        """

        # Plug in regressor
        model = SVR(kernel='poly', 
                    degree=3,
                    gamma='auto',
                    C=10, 
                    epsilon=0.1)
        model.fit(x_train, y_train)
        return model

    def get_test_prediction(self):
        """
        Override in your class if necessary
        :return: prediction result
        """
        x_train, x_test, y_train, y_scaler, model = self.get_validation_support()
        model.fit(x_train, y_train)
        prediction = model.predict(x_test)
        return y_scaler.inverse_transform(prediction.reshape(-1,1)).reshape(1,-1)[0]