import boto3, json, pprint, requests, textwrap, time, logging, requests
from datetime import datetime


region_name = 'us-east-1'


def client(region_name):
    global emr
    emr = boto3.client('emr', region_name=region_name)

def get_security_group_id(group_name, region_name):
    ec2 = boto3.client('ec2', region_name=region_name)
    response = ec2.describe_security_groups(GroupNames=[group_name])
    return response['SecurityGroups'][0]['GroupId']

def create_cluster(region_name, cluster_name='Keerthi_Cluster' + str(datetime.now()), release_label='emr-6.2.0',master_instance_type='m5.xlarge', num_core_nodes=2, core_node_instance_type='m5.xlarge'):
    emr_master_security_group_id = get_security_group_id('Keerthi_EMR', region_name=region_name)
    emr_slave_security_group_id = get_security_group_id('Keerthi_EMR', region_name=region_name)
    cluster_response = emr.run_job_flow(
        Name=cluster_name,
        ReleaseLabel=release_label,
        Instances={
            'InstanceGroups': [
                {
                    'Name': "Master nodes",
                    'Market': 'ON_DEMAND',
                    'InstanceRole': 'MASTER',
                    'InstanceType': master_instance_type,
                    'InstanceCount': 1
                },
                {
                    'Name': "Slave nodes",
                    'Market': 'ON_DEMAND',
                    'InstanceRole': 'CORE',
                    'InstanceType': core_node_instance_type,
                    'InstanceCount': num_core_nodes
                }
            ],
            'KeepJobFlowAliveWhenNoSteps': True,
            'Ec2KeyName' : 'Keerthikeypair',
            'EmrManagedMasterSecurityGroup': emr_master_security_group_id,
            'EmrManagedSlaveSecurityGroup': emr_slave_security_group_id
        },
		BootstrapActions= [
				{
					'Name': 'Install boto3',
					'ScriptBootstrapAction':{
							'Path': 's3://keerthilandingzone/Dependencies/dependecies.sh',
							}
						
					}
				],
		
		AutoTerminationPolicy = {"IdleTimeout" : 600},		
        VisibleToAllUsers=True,
        JobFlowRole='EMR_EC2_DefaultRole',
        ServiceRole='EMR_DefaultRole',
        Applications=[
            { 'Name': 'hadoop' },
            { 'Name': 'spark' },
            { 'Name': 'hive' },
            { 'Name': 'livy' },
            { 'Name': 'zeppelin' }
        ]
    )
    return cluster_response['JobFlowId']


def get_cluster_dns(cluster_id):
    response = emr.describe_cluster(ClusterId=cluster_id)
    return response['Cluster']['MasterPublicDnsName']


def wait_for_cluster_creation(cluster_id):
    emr.get_waiter('cluster_running').wait(ClusterId=cluster_id)


def terminate_cluster(cluster_id):
    emr.terminate_job_flows(JobFlowIds=[cluster_id])


def create_spark_session(master_dns,datasetName,spark_config_path,dataset_path):
    # 8998 is the port on which the Livy server runs
    host = 'http://' + master_dns + ':8998'
    data = {'file':"s3://keerthilandingzone/Codes/AWS_Final_Code.py",
            'args':[datasetName, spark_config_path, dataset_path]

    }
    headers = {'Content-Type': 'application/json'
              }

    response = requests.post(host + '/batches', data=json.dumps(data), headers=headers)
    logging.info(response.json())
    return response.headers


def track_statement_progress(master_dns, response_headers):
    statement_status = ''
    host = 'http://' + master_dns + ':8998'
    session_url = host + response_headers['location'].split('/statements', 1)[0]
    # Poll the status of the submitted scala code
    while statement_status != 'available':
        # If a statement takes longer than a few milliseconds to execute, Livy returns early and provides a statement URL that can be polled until it is complete:
        statement_url = host + response_headers['location']
        statement_response = requests.get(statement_url, headers={'Content-Type': 'application/json'})
        statement_status = statement_response.json()['state']
        logging.info('Statement status: ' + statement_status)

        #logging the logs
        lines = requests.get(session_url + '/log', headers={'Content-Type': 'application/json'}).json()['log']
        for line in lines:
            logging.info(line)

        if 'progress' in statement_response.json():
            logging.info('Progress: ' + str(statement_response.json()['progress']))
        time.sleep(10)
    final_statement_status = statement_response.json()['output']['status']
    if final_statement_status == 'error':
        logging.info('Statement exception: ' + statement_response.json()['output']['evalue'])
        for trace in statement_response.json()['output']['traceback']:
            logging.info(trace)
        raise ValueError('Final Statement Status: ' + final_statement_status)
    logging.info('Final Statement Status: ' + final_statement_status)


def get_public_ip(cluster_id):
    instances = emr.list_instances(ClusterId=cluster_id, InstanceGroupTypes=['MASTER'])
    return instances['Instances'][0]['PublicIpAddress']
