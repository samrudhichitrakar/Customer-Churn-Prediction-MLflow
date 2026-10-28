from pathlib import Path
import json, urllib.request, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import ks_2samp, chi2_contingency
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix, ConfusionMatrixDisplay
import mlflow, mlflow.sklearn

ROOT=Path(__file__).resolve().parent; DATA=ROOT/"data"; OUT=ROOT/"outputs"
DATA.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
URL="https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv"
def main():
    csv=DATA/"Telco-Customer-Churn.csv"
    if not csv.exists():
        print("Downloading Telco Customer Churn dataset...")
        urllib.request.urlretrieve(URL,csv)
    df=pd.read_csv(csv)
    if "Churn" not in df: raise ValueError("CSV does not contain Churn column.")
    if "customerID" in df: df=df.drop(columns=["customerID"])
    df["TotalCharges"]=pd.to_numeric(df["TotalCharges"],errors="coerce")
    df["Churn"]=df["Churn"].astype(str).str.strip().map({"Yes":1,"No":0})
    df=df.dropna(subset=["Churn"])
    X=df.drop(columns=["Churn"]); y=df["Churn"].astype(int)
    nums=X.select_dtypes(include=["number"]).columns.tolist(); cats=[c for c in X if c not in nums]
    prep=ColumnTransformer([
      ("num",Pipeline([("imputer",SimpleImputer(strategy="median")),("scale",StandardScaler())]),nums),
      ("cat",Pipeline([("imputer",SimpleImputer(strategy="most_frequent")),("onehot",OneHotEncoder(handle_unknown="ignore"))]),cats)])
    Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=.25,random_state=42,stratify=y)
    model=Pipeline([("prep",prep),("classifier",RandomForestClassifier(n_estimators=150,max_depth=12,random_state=42,class_weight="balanced",n_jobs=-1))])
    model.fit(Xtr,ytr); pred=model.predict(Xte); prob=model.predict_proba(Xte)[:,1]
    m={"accuracy":float(accuracy_score(yte,pred)),"precision":float(precision_score(yte,pred,zero_division=0)),
       "recall":float(recall_score(yte,pred,zero_division=0)),"f1":float(f1_score(yte,pred,zero_division=0)),
       "roc_auc":float(roc_auc_score(yte,prob)),"total_rows":int(len(df)),"training_rows":int(len(Xtr)),
       "test_rows":int(len(Xte)),"feature_count":int(X.shape[1]),"churn_rate":float(y.mean())}
    ref=Xte.copy(); cur=Xte.copy()
    if "MonthlyCharges" in cur: cur["MonthlyCharges"]=cur["MonthlyCharges"]*1.15
    if "tenure" in cur: cur["tenure"]=np.maximum(0,cur["tenure"]-6)
    if "Contract" in cur: cur["Contract"]=cur["Contract"].replace({"Month-to-month":"One year","One year":"Two year"})
    rows=[]
    for c in X.columns:
      if c in nums:
        stat,p=ks_2samp(pd.to_numeric(ref[c],errors="coerce").dropna(),pd.to_numeric(cur[c],errors="coerce").dropna())
      else:
        cats_all=sorted(set(ref[c].fillna("MISSING").astype(str))|set(cur[c].fillna("MISSING").astype(str)))
        tab=pd.DataFrame({"ref":ref[c].fillna("MISSING").astype(str).value_counts().reindex(cats_all,fill_value=0),
                          "cur":cur[c].fillna("MISSING").astype(str).value_counts().reindex(cats_all,fill_value=0)}).T
        try: stat,p,_,_=chi2_contingency(tab)
        except Exception: stat,p=0,1
      rows.append({"feature":c,"feature_type":"numeric" if c in nums else "categorical","test_statistic":float(stat),"p_value":float(p),"drift_detected":bool(p<.05)})
    drift=pd.DataFrame(rows).sort_values("p_value"); drift.to_csv(OUT/"drift_results.csv",index=False)
    m["drifted_feature_count"]=int(drift.drift_detected.sum()); m["drifted_features"]=drift.loc[drift.drift_detected,"feature"].tolist()
    d={"dataset_name":"IBM Telco Customer Churn","dataset_source":URL,"target":"Churn (Yes=1, No=0)","features":list(X.columns),
       "numeric_features":nums,"categorical_features":cats,
       "problem":"Predict whether a telecommunications customer will leave the service using account, service, and billing characteristics.",
       "drift_method":"KS two-sample test for numeric features; chi-square test for categorical features","drift_threshold":.05,"drift_is_simulated":True,"metrics":m}
    mlflow.set_tracking_uri("sqlite:///mlflow.db");mlflow.set_experiment("ISE2_Customer_Churn_Prediction")
    with mlflow.start_run(run_name="RandomForest_with_simulated_churn_drift") as run:
      for k,v in {"model":"RandomForestClassifier","n_estimators":150,"max_depth":12,"class_weight":"balanced","random_state":42,"drift_threshold":.05}.items(): mlflow.log_param(k,v)
      for k in ["accuracy","precision","recall","f1","roc_auc","drifted_feature_count","total_rows","training_rows"]: mlflow.log_metric(k,m[k])
      mlflow.log_artifact(str(OUT/"drift_results.csv")); mlflow.sklearn.log_model(
    model, 
    artifact_path="model", 
    skops_trusted_types=["numpy.dtype", "sklearn.tree._tree.Tree"]
)

      d["mlflow_run_id"]=run.info.run_id
    (OUT/"results.json").write_text(json.dumps(d,indent=2),encoding="utf-8")
    plt.figure(figsize=(9,5)); q=drift.sort_values("test_statistic")
    plt.barh(q.feature,q.test_statistic); plt.xlabel("Test statistic"); plt.title("Reference vs simulated current data drift"); plt.tight_layout(); plt.savefig(OUT/"drift_plot.png",dpi=160); plt.close()
    ConfusionMatrixDisplay(confusion_matrix(yte,pred),display_labels=["No Churn","Churn"]).plot()
    plt.title("Customer Churn Confusion Matrix"); plt.tight_layout(); plt.savefig(OUT/"confusion_matrix.png",dpi=160); plt.close()
    print("PROJECT COMPLETED")
    print(f"Rows: {m['total_rows']}; churn rate: {m['churn_rate']:.4f}")
    print(f"Accuracy={m['accuracy']:.4f}; Precision={m['precision']:.4f}; Recall={m['recall']:.4f}; F1={m['f1']:.4f}; ROC-AUC={m['roc_auc']:.4f}")
    print(f"Drifted features ({m['drifted_feature_count']}): {', '.join(m['drifted_features'])}")
    print("Run python generate_report.py next.")
if __name__=="__main__": main()
