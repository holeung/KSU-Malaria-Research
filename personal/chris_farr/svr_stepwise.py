import pandas as pd
import numpy as np
from sklearn.model_selection import GridSearchCV, RepeatedStratifiedKFold
from sklearn.metrics import make_scorer, r2_score
from sklearn.svm import LinearSVR
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import MiniBatchKMeans
from src.model_validation import ModelValidation

# if __name__ == "__main__":
# Load data
print("loading data....")
df = pd.read_csv("src/data/source_data/Series3_6.15.17_padel.csv", index_col=0)
# Eliminate features without variance
df = df.loc[:, (df.std() > 0).values]
# Split x, y
y_data = df.pop("IC50")
# y_class = pd.Series(data=[int(y < 2.1) for y in y_data])
x_data = df.copy()

# Remove columns with missing data
x_data = x_data.dropna(axis=1)

# Transform discrete with one-hot-encoding
int_cols = x_data.columns[x_data.dtypes == 'int64']
float_cols = x_data.columns[x_data.dtypes == 'float64']
one_hot_df = pd.get_dummies(x_data[int_cols].astype('O'))
x_data = pd.merge(x_data[float_cols], one_hot_df, left_index=True, right_index=True)

# Ensure no (+/-) inf or nan due to improper transformation
x_data.replace([np.inf, -np.inf], np.nan, inplace=True)
assert not sum(x_data.isna().sum()), "Unexpected nulls found"

# Perform feature engineering on float columns
print("performing non-linear transformations....\n")
for feat in x_data.columns[x_data.dtypes == 'float64']:
    feature_df = x_data.loc[:, feat]
    if feature_df.min() > 0:  # Avoid 0 or negative
        x_data.loc[:, feat + "_log"] = feature_df.apply(np.log)  # log
        x_data.loc[:, feat + "_log2"] = feature_df.apply(np.log2)  # log2
        x_data.loc[:, feat + "_log10"] = feature_df.apply(np.log10)  # log10
        x_data.loc[:, feat + "_cubert"] = feature_df.apply(
            lambda x: np.power(x, 1 / 3))  # cube root
        x_data.loc[:, feat + "_sqrt"] = feature_df.apply(np.sqrt)  # square root
    # Avoid extremely large values, keep around 1M max
    if feature_df.max() < 13:
        x_data.loc[:, feat + "_exp"] = feature_df.apply(np.exp)  # exp
    if feature_df.max() < 20:
        x_data.loc[:, feat + "_exp2"] = feature_df.apply(np.exp2)  # exp2
    if feature_df.max() < 100:
        x_data.loc[:, feat + "_cube"] = feature_df.apply(
            lambda x: np.power(x, 3))  # cube
    if feature_df.max() < 1000:
        x_data.loc[:, feat + "_sq"] = feature_df.apply(np.square)  # square

# Seperate Series 3 test when IC50 is null
test_index = y_data.isnull()
x_train = x_data.loc[~test_index].copy()
y_train = y_data.loc[~test_index].copy()
x_test = x_data.loc[test_index].copy()


"""
1. Group normalized features with cosine similarity of >.999(tune), select only one feature 
from groups of identical features
2. Cluster remaining features using k-means (which from what I've read, euclidean distance 
is a linear equivalent to cosine similarity, reference added below) into an arbitrary number of groups.
(95% of feature space size)
3. Use a model to extract feature importance and select a portion for removal, for the 
group slated for removal those will be sorted by the number of features in their cluster, favoring 
features that have the most features similar to them for final removal in that iteration.
* note clustering is done with all features, not just those for removal
4. After a handful are removed, rerun the cluster analysis to reset the group numbers and continue 
until 5% of the starting features are removed
5. Repeat
"""

# Normalize
x_scaler = StandardScaler()
y_scaler = StandardScaler()


x_train.loc[:, :] = x_scaler.fit_transform(x_train)
x_test.loc[:, :] = x_scaler.transform(x_test)
y_train.loc[:] = np.squeeze(y_scaler.fit_transform(y_train.values.reshape(-1, 1)))

# TODO START HERE!!

""" 
@Note: feature engineering should probably output a list of features instead of including
it in the implementation pipeline... otherwise it could get too heavy. stepwise for example
"""

# Establish benchmark
print("Establishing benchmark....")
model = LinearSVR(random_state=0, C=0.05)
ModelValidation().score_regressor(x_train, y_train, model, pos_split=y_scaler.transform([[2.1]]))
print("\n")

# Group features by cosine similarity only one from each group with .999 cosine similarity
selected_feats = set(x_data.columns)
print("Grouping highly correlated features....\n")
while True:
    # Loop to ensure all are removed, naive approach used for grouping

    corr_threshold = .95
    corr_matrix = x_data.corr()
    corr_matrix.loc[:, :] = np.tril(corr_matrix, k=-1)  # borrowed from Karl D's answer

    already_in = set()
    corr_result = []
    for col in corr_matrix:
        correlated = corr_matrix[col][np.abs(corr_matrix[col]) > corr_threshold].index.tolist()
        if correlated and col not in already_in:
            already_in.update(set(correlated))
            correlated.append(col)
            corr_result.append(correlated)
        elif col not in already_in:
            already_in.update(set([col]))
            corr_result.append([col])

    all_feats = set(list(x_data.loc[:, selected_feats].columns))
    selected_feats = set([feats[0] for feats in corr_result])
    removed_feats = all_feats - selected_feats

    print("all_feats %s" % len(all_feats))
    print("selected_feats %s" % len(selected_feats))
    print("removed_feats %s \n" % len(removed_feats))

    if not removed_feats:
        break

# Filter to only selected features
x_copy = x_train.loc[:, selected_feats]
# Measure starting benchmark
print("new benchmark....")
model = LinearSVR(random_state=0, C=.05)
benchmark = ModelValidation().score_regressor(x_copy, y_train, model, pos_split=y_scaler.transform([[2.1]]))
print("\n")

len(selected_feats)
sel_array = np.array(selected_feats)

# Misc setup for loop
best_C = None
i = 0  # Used to control improvement patience
best_features = selected_feats  # Start off with selected_features so far

while True:

    # Filter to only selected features
    x_copy = x_data.loc[:, selected_feats]

    # Cluster remaining features using k-means
    batch_size = int(len(selected_feats) / 25)
    clusters = int(len(selected_feats) * .95)
    kmeans = MiniBatchKMeans(n_clusters=clusters,
                             batch_size=batch_size,
                             init_size=3 * clusters)
    kmeans.fit(x_copy.transpose())

    # Extract group label and get counts, store as label_counts dict
    k, v = np.unique(kmeans.labels_, return_counts=True)
    label_counts = dict(zip(k, v))
    # Create array with total group counts for each label in the dataset
    feat_group_count = np.array([label_counts[feat] for feat in kmeans.labels_])
    # Normalize and reverse sign to align higher group-size and lower coef for scoring
    feat_group_count_n = StandardScaler().fit_transform(feat_group_count.reshape(-1, 1).astype(np.float)) * -1
    feat_group_count_n = np.squeeze(feat_group_count_n)

    # Use a model to extract feature importance and select a portion for removal

    # Tune the model with - features
    model = LinearSVR(random_state=0)

    if best_C is not None:
        # Allow C to drift through process, but restrict range for efficiency/fine-tune tradeoff
        start_range = max(best_C * .8, 0.05)  # .8 lower, 1.3 upper to try to push C value up
        stop_range = min(best_C * 1.3, 1)
        params = {"C": np.arange(start_range, stop_range, (stop_range - start_range) / 10)}
    else:
        params = {"C": np.arange(.05, .5, .05)}

    grid = GridSearchCV(model, param_grid=params, scoring=make_scorer(r2_score, greater_is_better=True), cv=10, n_jobs=7)
    grid.fit(x_copy.loc[:, selected_feats], y_data)

    # Keep track of C for more efficient tuning
    best_C = grid.best_params_["C"]

    # create splits using stratified kfold
    rskf = RepeatedStratifiedKFold(n_splits=sum(y_class), n_repeats=5, random_state=0)
    # loop through splits
    feature_importances = []
    tracking_dict = dict()
    tracking_dict["r2_score"] = []
    tracking_dict["coefs"] = []
    for train, test in rskf.split(x_copy, y_class):
        x_train, x_test = x_copy.iloc[train, :], x_copy.iloc[test, :]
        y_train, y_test = y_data.iloc[train], y_data.iloc[test]
        # train model, test model with all scoring parameters
        model = LinearSVR(random_state=0, C=best_C)
        model.fit(x_train, y_train)
        y_ = model.predict(X=x_test)
        # append scores to logging dictionary
        tracking_dict["r2_score"].append(r2_score(y_test, y_))
        tracking_dict["coefs"].append(model.coef_)

    coef_array = np.array(tracking_dict["coefs"])
    coef_array.shape

    # Which columns have the highest absolute average value
    coef_array = np.abs(coef_array)
    coef_array = np.mean(coef_array, axis=0)
    coef_array_n = StandardScaler().fit_transform(coef_array.reshape(-1, 1))
    coef_array_n = np.squeeze(coef_array_n)

    # 50/50 weight the importance and the cluster group values
    assert len(feat_group_count_n) == len(coef_array_n), "uneven lengths"

    score_array = feat_group_count_n * .5 + coef_array_n * .5

    percentile_slicer = np.percentile(score_array, 5)
    selected_feats = [feat for feat, imprnt in zip(x_data.columns, score_array) if imprnt > percentile_slicer]

    # Print round summary
    print("Round summary....")
    print("tuning r2 score: %s" % np.mean(tracking_dict["r2_score"]))
    print("best_C: %s" % best_C)
    print("selected features: %s" % len(selected_feats))
    # Measure benchmark
    print("New benchmark....")
    model = LinearSVR(random_state=0, C=best_C)
    new_benchmark = ModelValidation().score_regressor(x_data.loc[:, selected_feats], y_data, model,
                                                      pos_split=y_scaler.transform([[2.1]]))
    print("\n")
    if np.mean(new_benchmark["r2_score"]) < np.mean(benchmark["r2_score"]):
        i += 1
        if i > 5:
            break
    else:
        i = 0
        best_features = selected_feats
        benchmark = new_benchmark

# Final benchmark
print("Final benchmark....")
model = LinearSVR(random_state=0, C=best_C)
ModelValidation().score_regressor(x_data.loc[:, best_features], y_data, model,
                                  pos_split=y_scaler.transform([[2.1]]))


# correlation threshold: .99, percentile 5
# Final benchmark....
# with 3 splits and 10 repeats
# average r2_score: 0.19215420413702972
# average rmse: 0.8675296458146753
