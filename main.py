#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
import botocore
import boto3

REGION = 'cn-northwest-1'
PREFIX = 'disk-image/'
ROLE_NAME = 'vmimport'

sess = boto3.Session(region_name=REGION)
ec2 = sess.resource('ec2')
iam = sess.resource('iam')
s3 = sess.resource('s3')


def get_options(args=None):
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(description='Parse arguments.')
    parser.add_argument("-i", "--input", help="Your disk image's path")
    parser.add_argument("-b", "--bucket", help="S3 bucket to store your disk image")
    cmd_options = parser.parse_args(args)
    return cmd_options


options = get_options(sys.argv[1:])
path = options.input
bucket_name = options.bucket
file_name = os.path.basename(path)
bucket = s3.Bucket(bucket_name)
s3_obj_key = PREFIX + file_name

# 不存在也不会报错
s3_obj = bucket.Object(s3_obj_key)
vmimport_role = iam.Role(ROLE_NAME)

# 判断 disk image 文件是否存在
if not os.path.isfile(path):
    print("Please input correct file path. Error path: {}".format(path))
    exit(1)

# 判断 bucket 是否存在,
try:
    s3.meta.client.head_bucket(Bucket=bucket_name)
except botocore.exceptions.ClientError as err:
    if err.response['Error']['Code'] == '404':
        print("Bucket {} doesn't exist".format(bucket_name))
        exit(1)


# upload to S3
def image_upload():
    with open(path, 'rb') as data:
        print("File is being uploaded to S3.")
        s3_obj.upload_fileobj(data)
    print("Uploading is finished.")
    return s3_obj


# create role for import
def role_create():
    trust_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "vmie.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "sts:Externalid": "vmimport"
                    }
                }
            }
        ]
    }

    role = iam.create_role(
        RoleName=ROLE_NAME,
        AssumeRolePolicyDocument=json.dumps(trust_policy_doc),
        Description=''
    )

    role_policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetBucketLocation",
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    "arn:aws-cn:s3:::" + bucket_name,
                    "arn:aws-cn:s3:::" + bucket_name + "/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetBucketLocation",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:PutObject",
                    "s3:GetBucketAcl"
                ],
                "Resource": [
                    "arn:aws-cn:s3:::" + bucket_name,
                    "arn:aws-cn:s3:::" + bucket_name + "/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:ModifySnapshotAttribute",
                    "ec2:CopySnapshot",
                    "ec2:RegisterImage",
                    "ec2:Describe*"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "kms:CreateGrant",
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:Encrypt",
                    "kms:GenerateDataKey*",
                    "kms:ReEncrypt*"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "license-manager:GetLicenseConfiguration",
                    "license-manager:UpdateLicenseSpecificationsForResource",
                    "license-manager:ListLicenseSpecificationsForResource"
                ],
                "Resource": "*"
            }
        ]
    }

    # inline policy
    policy_name = 'vmimport'
    role_policy = iam.RolePolicy(role.name, policy_name)
    role_policy.put(
        PolicyDocument=json.dumps(role_policy_doc)
    )
    print("Role is created.")
    return role


# import image
def main():
    global s3_obj, vmimport_role

    # role 不存在则创建
    if vmimport_role not in iam.roles.all():
        vmimport_role = role_create()
        vmimport_role.load()
    else:
        print("Role {} already exists.".format(vmimport_role.name))

    # 文件如果 S3 中不存在则上传
    try:
        s3.meta.client.head_object(
            Bucket=bucket_name,
            Key=s3_obj.key
        )
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == '404':
            s3_obj = image_upload()

    # 开始导入
    response = ec2.meta.client.import_image(
        Architecture='x86_64',
        DiskContainers=[
            {
                'Description': 'System Disk',
                'DeviceName': '/dev/sda',
                'Format': 'OVA',
                'UserBucket': {
                    'S3Bucket': s3_obj.bucket_name,
                    'S3Key': s3_obj.key
                }
            },
        ],
        LicenseType='BYOL',
        Platform='Windows',
        RoleName=vmimport_role.name
    )

    import_task_id = response.get('ImportTaskId')
    response = ec2.meta.client.describe_import_image_tasks(
        ImportTaskIds=[
            import_task_id,
        ]
    )
    task_status = response.get('ImportImageTasks')[0].get('Status')
    print("Task {} is at {} status.".format(import_task_id, task_status))


if __name__ == "__main__":
    main()
