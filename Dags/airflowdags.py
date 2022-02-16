import emrlib.emrplugin as emr 
import boto3
import json
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from pyspark.sql import SparkSession
from airflow.providers.amazon.aws.operators.s3_copy_object import S3CopyObjectOperator
import pandas as pd
import pyarrow.parquet as pq


def get_response(**kwargs): 
    ti = kwargs['ti'] 
    data = dict() 
    for key, value in kwargs["params"].items(): 
        data[key] = value 
    ti.xcom_push(key="data",value=data)


def app_config(ti):
    #s3 = boto3.resource('s3')
    #content_object = s3.Object('keerthilandingzone', 'Conf/app_conf.json')
    #file_content = content_object.get()['Body'].read().decode('utf-8')
    #json_content = json.loads(file_content)
    #land_zone = json_content['landing-bucket']
    #raw_zone = json_content['raw-bucket']
    #ti.xcom_push(key='landing-bucket', value=land_zone)
    #ti.xcom_push(key='raw_bucket', value=raw_zone)
    #print(raw_zone, staging_zone)
    
    pass

def data_trf(**kwargs):
    ti = kwargs['ti']
    s3 = boto3.resource('s3')
    content_object = s3.Object('keerthilandingzone', 'Conf/app_conf.json')
    file_content = content_object.get()['Body'].read().decode('utf-8')
    json_content = json.loads(file_content)
    land_zone = json_content['landing-bucket']
    raw_zone = json_content['raw-bucket']
    key = ti.xcom_pull(key="data")['key']

    copy_source = {

        'Bucket': land_zone,

        'Key': key

    }
    
    s3.meta.client.copy(copy_source, raw_zone, key)



def pre_validation():
    s2 = boto3.resource('s3')
    s3 = s3fs.S3FileSystem()
    content_object = s2.Object('keerthilandingzone', 'Conf/app_conf.json')
    file_content = content_object.get()['Body'].read().decode('utf-8')
    json_content = json.loads(file_content)
    key = ti.xcom_pull(key="data")['key']
    land_zone = "s3://"+json_content['landing-bucket']+"/"+key
    raw_zone ="s3://"+ json_content['raw-bucket']+"/"+key


    df_landingzone = pq.ParquetDataset(land_zone, filesystem=s3).read_pandas().to_pandas()
    df_rawzone = pq.ParquetDataset(land_zone, filesystem=s3).read_pandas().to_pandas()

    if df_rawzone[df_rawzone.columns[0]].count()!=0:
        for raw_columnname in df_rawzone.columns:
            if df_rawzone[raw_columnname].count() == df_landingzone[raw_columnname].count():
                print("Count satisfied with", str(raw_columnname))
            else:
                print("Check mismatch", str(raw_columnname))

    else:
        print("No Data Available")
    

def livy_submit(**kwargs):
    ti = kwargs['ti']
    region = 'us-east-1'
    emr.client(region_name=region)
    cluster_id = emr.create_cluster(region_name=region, cluster_name='Keerthi_Cluster', num_core_nodes=1)
    emr.wait_for_cluster_creation(cluster_id)
    cluster_dns = emr.get_cluster_dns(cluster_id)
    headers = emr.create_spark_session(cluster_dns,ti.xcom_pull(key="data")['datasetName'],ti.xcom_pull(key="data")['spark_config_path'],ti.xcom_pull(key="data")['key'])
    #session_status = emr.track_statement_progress(cluster_dns, headers)
    #return session_status
    
    
    
def post_validation():
    pass
    

dag_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2022, 1, 23),
    'email': ['keerthivasan.kan@tigeranalytics.com'],
    'email_on_failure': True,
    'email_on_retry': True,
    'retries': 1,
    'retry_delay': timedelta(minutes=3)
    }

dag = DAG(
    dag_id='AAA_EMR_Test',
    start_date=datetime(2022, 1, 23),
    default_args=dag_args,
    end_date=None,
    catchup=False,
    schedule_interval='@once')
   
get_response = PythonOperator(
        task_id="get_response",
        python_callable=get_response,
        dag=dag)    


app_config = PythonOperator(
        task_id="app_config",
        python_callable=app_config,
        dag=dag)

data_trf = PythonOperator(
        task_id="data_trf",
        python_callable=data_trf,
        dag=dag)

pre_validation = PythonOperator(
        task_id="pre_validation",
        python_callable=pre_validation,
        dag=dag)
        
livy_submit = PythonOperator(
        task_id="livy_submit",
        python_callable=livy_submit,
        dag=dag)
        
post_validation = PythonOperator(
        task_id="post_validation",
        python_callable=post_validation,
        dag=dag)


get_response >> app_config >> data_trf >> pre_validation>>livy_submit>>post_validation
