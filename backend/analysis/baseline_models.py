from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from analysis.ml_features import Winsorizer


def make_logistic():
    return make_pipeline(
        Winsorizer(),
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )
