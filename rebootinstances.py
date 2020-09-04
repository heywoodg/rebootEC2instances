import json, boto3, time, os
from datetime import datetime, timedelta

#############################################################
# Greg Heywood                                              #
# v 1.2                                                     #
#############################################################
# Run on a schedule, and set the maximum execution time!    #
# Set the variables in the Lmabda configuration             #
# - You may need to look at the metric dimensions.....      #
#    depending on how they are configured.                  #
#############################################################

# The script will:
# Get the target group
# get the instances
# check number of healthy instances. Break if less than three
# For each instance check cloudwatch metric
# For first one that has RAM high (or one with highest RAM)?
# If higher than 80%, remove from TG and reboot
# Add back in to TG

# 1.2 moved AMI check to the instance loop.

elbv2 = boto3.client('elbv2')
ec2 = boto3.resource('ec2')
ec2c = boto3.client('ec2')
cloudwatch = boto3.client('cloudwatch')



def lambda_handler(event, context):
    targetGroupName = 'tg1'
    targetGroupName80 = 'tg1-80'
    autoScalingGroup = 'autoScalingGroup'      
    
    instanceMem = {}
    tgDelay = 0 
    myCount = 0
    myCount80 = 0
    tgInstances = []
    
    # Get the ARN of the Target Group
    response = elbv2.describe_target_groups(
        Names=[
            targetGroupName,
        ],
    )
    # The main TG
    targetGroupArn = response['TargetGroups'][0]['TargetGroupArn']
    response = elbv2.describe_target_groups(
        Names=[
            targetGroupName80,
        ],
    )
    # The TG for port 80
    targetGroupArn80 = response['TargetGroups'][0]['TargetGroupArn']
    
    # Get the deregistration delay value
    response = elbv2.describe_target_group_attributes(
        TargetGroupArn=targetGroupArn
    )
    tgDelay=response['Attributes'][2]['Value']
    
    # Check if healthy hosts is great than 5 in the main TG:
    response = elbv2.describe_target_health(
        TargetGroupArn=targetGroupArn,
    )
    for x in response['TargetHealthDescriptions']:
        tgInstances.append(x['Target']['Id'])
        if x['TargetHealth']['State'] == 'healthy':
            myCount +=1
    print(str(myCount) + " healthy hosts")

    # Check if healthy hosts is great than 3 in the port 80 TG:
    response = elbv2.describe_target_health(
        TargetGroupArn=targetGroupArn80,
    )
    for x in response['TargetHealthDescriptions']:
        #tgInstances.append(x['Target']['Id'])
        if x['TargetHealth']['State'] == 'healthy':
            myCount80 +=1
    print(str(myCount80) + " healthy hosts")

    if (myCount <= 5) or (myCount80 <= 5):
        print(str(myCount) + ' healthy hosts in 443 TG.')
        print(str(myCount80) + ' healthy hosts in port 80. Terminating.')
        return
    
    # get the instance ID of the host that triggered the alarm
    #message = json.loads(event['Records'][0]['Sns']['Message'])
    #instanceId = message['Trigger']['Dimensions'][0]['value']
    #print('InstanceId = ' + instanceId)
    

    # get hosts % RAM metric

    for x in tgInstances:
        # Get the AMI ID from the instance #
        response = ec2c.describe_instances(
            InstanceIds=[
                x
            ]
        )
        ami = response['Reservations'][0]['Instances'][0]['ImageId']
        instanceType = response['Reservations'][0]['Instances'][0]['InstanceType']

        response = cloudwatch.get_metric_statistics(
            Namespace='CWAgent',
            MetricName='Memory % Committed Bytes In Use',
            Dimensions=[
                {
                    "Name": "InstanceId",
                    "Value": x
                },
                {
                    "Name": "AutoScalingGroupName",
                    "Value": autoScalingGroup 
                },
                {
                    "Name": "ImageId",
                    "Value": ami
                },
                {
                    "Name": "objectname",
                    "Value": "Memory"
                },
                {
                    "Name": "InstanceType",
                    "Value": instanceType
                }
            ],
            StartTime=datetime.utcnow() - timedelta(seconds=300),
            EndTime=datetime.utcnow(),
            Period=300,
            Statistics=[
                'Average'
            ]
        )
        #Add an entry to the dictionary with instance ID and the Average RAM
        print(x,":",response['Datapoints'][0]['Average'])
        instanceMem[x]=response['Datapoints'][0]['Average']
    
    
    #Find the instance with the highest used RAM
    instanceId = sorted(instanceMem, key=instanceMem.__getitem__)[-1]
    print('Instance with highest RAM load: ' + instanceId)
    print('Memory used: ' + str(instanceMem[instanceId]))
    

    if instanceMem[instanceId] > 65:
        print('Memory too high, going to reboot.')

        # remove the instance from the TGs
        print('Removing from the target groups.')
        response = elbv2.deregister_targets(
            TargetGroupArn=targetGroupArn,
            Targets=[
                {
                    'Id': instanceId,
                    'Port': 443
                },
            ]
        )
        print(response)      
        
        response = elbv2.deregister_targets(
            TargetGroupArn=targetGroupArn80,
            Targets=[
                {
                    'Id': instanceId,
                    'Port': 80
                },
            ]
        )
        print(response)    
        
        
        # Wait for the instance to degregister
        print('Waiting for degregistration from TG...')
        print('Target group delay: ', tgDelay)
        time.sleep(int(tgDelay))  
        
        # Reboot it
        print('Performing reboot')
        response = ec2c.reboot_instances(
            InstanceIds=[
                instanceId,
            ],
            DryRun=False
        )
        print(response)

        # Wait for the instance to start
        print('Waiting before placing the instance back in the TG...')
        time.sleep(120)  
        
        # add it back to the TGs
        print('Adding ' + instanceId + ' to the TG')
        response = elbv2.register_targets(
            TargetGroupArn=targetGroupArn,
            Targets=[
                {
                    'Id': instanceId,
                    'Port': 443
                },
            ]
        )
        print(response)
        response = elbv2.register_targets(
            TargetGroupArn=targetGroupArn80,
            Targets=[
                {
                    'Id': instanceId,
                    'Port': 80
                },
            ]
        )
        print(response)

