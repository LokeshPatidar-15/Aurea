import argparse

from analysis.baseline_models import make_logistic
from analysis.ml_features import load_model_frame
from analysis.tuning import load_best_params
from analysis.walkforward import run_walk_forward, summarize
from analysis.xgb_model import DEFAULT_PARAMS, fit_xgb, fit_xgb_final, predict_xgb
from services.model_store import save_artifact

HORIZON, K, FOLDS = 12, 2.0, 5


def train(symbol: str, timeframe: str, model_type: str) -> None:
    X, labels = load_model_frame(symbol, timeframe, HORIZON, K)
    params = None
    if model_type == "xgboost":
        params = {**DEFAULT_PARAMS, **(load_best_params(symbol, timeframe) or {})}

        def fit_predict(X_tr, y_tr, X_te):
            return predict_xgb(fit_xgb(X_tr, y_tr, HORIZON, params), X_te)

        def fit_final():
            return fit_xgb_final(X, labels["label"], HORIZON, params), [-1, 0, 1]
    else:
        def fit_predict(X_tr, y_tr, X_te):
            return make_logistic().fit(X_tr, y_tr).predict(X_te)

        def fit_final():
            model = make_logistic().fit(X, labels["label"])
            return model, [int(c) for c in model.classes_]

    table, pooled = run_walk_forward(X, labels, fit_predict, FOLDS)
    summary = summarize(table, pooled)
    model, class_order = fit_final()

    path = save_artifact(symbol, timeframe, {
        "model": model,
        "model_type": model_type,
        "class_order": class_order,
        "feature_names": list(X.columns),
        "horizon": HORIZON,
        "k": K,
        "params": params,
        "trained_through": X.index[-1].isoformat(),
        "trained_rows": int(len(X)),
        "walk_forward": summary,
    })
    size_kb = path.stat().st_size / 1024
    print(
        f"{symbol:8} {timeframe:3} {model_type:9} rows {len(X):5} | walk-forward bal.acc {summary['mean_balanced_accuracy']:.3f} "
        f"| net {summary['mean_net_bps_per_trade']:6.1f} bps/trade | saved {path.name} ({size_kb:.0f} KB)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and save the signal model.")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "XAUUSD", "EURUSD"])
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--model", choices=["xgboost", "logistic"], default="xgboost")
    args = parser.parse_args()
    for symbol in args.symbols:
        train(symbol, args.timeframe, args.model)


if __name__ == "__main__":
    main()
