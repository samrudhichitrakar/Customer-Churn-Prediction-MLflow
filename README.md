# ISE-2 Customer Churn Prediction using MLflow

## Run in Windows PowerShell
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_project.py
python generate_report.py
```
If activation is blocked: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again.

## MLflow UI
In another PowerShell window:
```powershell
mlflow ui --backend-store-uri ./mlruns --host 127.0.0.1 --port 5000
```
Open http://127.0.0.1:5000.

The first run downloads the IBM Telco Customer Churn CSV. The model is a RandomForestClassifier. Numeric fields are imputed/scaled and categorical fields imputed/one-hot encoded. Drift is simulated by increasing MonthlyCharges, reducing tenure, and shifting Contract categories. Numeric fields use a two-sample KS test; categorical fields use a chi-square test. A p-value below 0.05 flags a feature. This is a demonstration of simulated drift, not observed production drift.
