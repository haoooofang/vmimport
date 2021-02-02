#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys

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
obj_key = PREFIX + file_name

s3_obj = bucket.Object(obj_key)
vmimport_role = iam.Role(ROLE_NAME)

# 判断 disk image 文件是否存在
if not os.path.isfile(path):
    print("Please input correct file path. Error path: {}".format(path))
    exit(1)

# 判断 bucket 是否存在,
if bucket_name not in [i.name for i in s3.buckets.all()]:
    print("Bucket {} doesn't exist".format(bucket_name))
    exit(1)


# upload to S3
def image_upload():
    with open(path, 'rb') as data:
        s3_obj.upload_fileobj(data)
    print("File is uploaded.")
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
                    "arn:vmimport-cn:s3:::" + bucket_name,
                    "arn:vmimport-cn:s3:::" + bucket_name + "/*"
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
                    "arn:vmimport-cn:s3:::" + bucket_name,
                    "arn:vmimport-cn:s3:::" + bucket_name + "/*"
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
    if s3_obj not in bucket.objects.all():
        s3_obj = image_upload()
    if vmimport_role not in iam.roles.all():
        vmimport_role = role_create()
        vmimport_role.load()
    response = ec2.meta.client.import_image(
        Architecture='amd64',
        DiskContainers=[
            {
                'Description': 'System Disk',
                'DeviceName': '/dev/sda',
                'Format': 'VMDK',
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
    print(task_status)


if __name__ == "__main__":
    main()
