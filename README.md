# 一键导入 Windows 虚机镜像
## 运行方式
1. 给予 main.py 运行权限;
2. ./main.py -i 磁盘镜像文件 -b bucket名称.

## 注意事项
1. 预设定为宁夏区域, 北京区域请修改 REGION;
2. 运行的机器需有 EC2, S3, IAM 相应权限;
3. 程序运行成功后, 仍需等待任务完成, 需要 1-2 小时；
4. 关于镜像格式等更多信息, 请参考 https://docs.aws.amazon.com/vm-import/latest/userguide/vmie_prereqs.html
5. 预设为 OVA 格式镜像, 其它格式要求请参考上方链接.