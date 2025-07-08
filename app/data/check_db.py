import pandas as pd
import sqlite3

# Connect to your database
conn = sqlite3.connect('zus_outlets.db')

# Read a table into a DataFrame
df = pd.read_sql_query("SELECT * FROM outlets", conn)

# Show the first few rows
print("head:", df.head())
print("tail:", df.tail())
print("columns:", df.columns)
print("info:", df.info())
print("describe:", df.describe())
print("shape:", df.shape)
print("dtypes:", df.dtypes)

# Or, in Jupyter/Streamlit, use display(df) or st.dataframe(df)