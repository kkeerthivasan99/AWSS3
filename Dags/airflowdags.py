import EMR_Creation as emr
import boto3
import json
from airflow import DAG
from airflow.providers.amazon.aws.operators.s3_copy_object import S3CopyObjectOperator
import boto3, s3fs
import json
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import pandas as pd
import pyarrow.parquet as pq



def get_response(**kwargs):
    ti = kwargs['ti']
    data = dict()
    for key, value in kwargs["params"].items():
        data[key] = value
    ti.xcom_push(key="data",value=data)


def app_config(**kwargs):
    s3 = boto3.resource('s3')
    ti = kwargs['ti']
    conf = ti.xcom_pull(key="data")
    app_config_bucket = conf["app_config_bucket"]
    app_config_path = conf['app_config_path']
    dataset_name = conf['datasetName']
    content_object = s3.Object(app_config_bucket, app_config_path)
    file_content = content_object.get()['Body'].read().decode('utf-8')
    json_content = json.loads(file_content)

    locs = dict()
    locs['landing-bucket'] = json_content['landing-bucket']
    locs['raw-bucket'] = json_content['raw-bucket']
    locs['staging-bucket'] = json_content['staging-bucket']
    locs['datatype_update_cols'] = json_content['mask-'+dataset_name]['datatype-update-cols']

    locs['dataset_source'] = json_content['ingest-'+dataset_name]['source']['data-location']
    locs['dataset_dest'] = json_content['ingest-'+dataset_name]['destination']['data-location']

    ti.xcom_push(key="Bucket_locations",value=locs)



def data_trf(**kwargs):
    ti = kwargs['ti']
    s3 = boto3.resource('s3')
    key = ti.xcom_pull(key="data")['key']
    json_content = ti.xcom_pull(key='Bucket_locations')
    land_zone = json_content['landing-bucket']
    raw_zone = json_content['raw-bucket']
    key = ti.xcom_pull(key="data")['key']

    copy_source = {

        'Bucket': land_zone,

        'Key': key

    }

    s3.meta.client.copy(copy_source, raw_zone, key)



def pre_validation(**kwargs):
    pass






def livy_submit(**kwargs):
    ti = kwargs['ti']
    region = 'us-east-1'
    emr.client(region_name=region)
    cluster_id = emr.create_cluster(region_name=region, cluster_name='Keerthi_Cluster', num_core_nodes=1)
    emr.wait_for_cluster_creation(cluster_id)
    cluster_dns = emr.get_cluster_dns(cluster_id)
    headers = emr.create_spark_session(cluster_dns,ti.xcom_pull(key="data")['datasetName'],ti.xcom_pull(key="data")['spark_config_path'],ti.xcom_pull(key="data")['key'])



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
    dag_id='AAA_EMR_TestV3',
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

