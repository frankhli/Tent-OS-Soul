"""Tent OS CLI —— 命令行工具

支持命令:
    tent-os init                          初始化项目配置文件
    tent-os doctor                        系统诊断
    tent-os onboard                       交互式首次配置
    tent-os worker memory                 启动记忆进程
    tent-os worker governance             启动治理进程
    tent-os worker scheduler              启动调度进程
    tent-os gateway webhook               启动 Webhook Gateway
    tent-os server --port 8000            启动 HTTP API Server
    tent-os run                           单进程启动所有组件（开发模式）
"""

import argparse
import asyncio
import logging
import sys

from tent_os.bootstrap import init_project, run_worker_forever
from tent_os.api.server import run_api_server
from tent_os.logging_config import setup_logging
from tent_os.main import TentOS
from tent_os.doctor import Doctor, print_report
from tent_os.onboarding import run_onboarding
from tent_os.hot_reload import run_with_reload


def main():
    parser = argparse.ArgumentParser(
        prog="tent-os",
        description="Tent OS —— 去AI化的智能体内核"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # init
    subparsers.add_parser("init", help="初始化项目配置文件")
    
    # doctor
    doctor_parser = subparsers.add_parser("doctor", help="系统诊断检查")
    doctor_parser.add_argument(
        "--config", "-c",
        default="./config/tent_os.yaml",
        help="配置文件路径 (默认: ./config/tent_os.yaml)"
    )
    
    # onboarding
    subparsers.add_parser("onboard", help="交互式首次配置引导")
    
    # worker
    worker_parser = subparsers.add_parser("worker", help="启动工作进程")
    worker_parser.add_argument(
        "worker_type",
        choices=["memory", "governance", "scheduler"],
        help="工作进程类型"
    )
    worker_parser.add_argument(
        "--config", "-c",
        default="./config/tent_os.yaml",
        help="配置文件路径 (默认: ./config/tent_os.yaml)"
    )
    
    # gateway
    gateway_parser = subparsers.add_parser("gateway", help="启动网关")
    gateway_parser.add_argument(
        "gateway_type",
        choices=["webhook"],
        help="网关类型"
    )
    gateway_parser.add_argument(
        "--config", "-c",
        default="./config/tent_os.yaml",
        help="配置文件路径"
    )
    
    # server
    server_parser = subparsers.add_parser("server", help="启动 HTTP API Server")
    server_parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="监听端口 (默认: 8000)"
    )
    server_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="监听地址 (默认: 0.0.0.0)"
    )
    server_parser.add_argument(
        "--config", "-c",
        default="./config/tent_os.yaml",
        help="配置文件路径"
    )
    
    # run (开发模式，单进程启动所有组件)
    run_parser = subparsers.add_parser("run", help="单进程启动所有组件（开发模式）")
    run_parser.add_argument(
        "--config", "-c",
        default="./config/tent_os.yaml",
        help="配置文件路径"
    )
    run_parser.add_argument(
        "--reload", "-r",
        action="store_true",
        help="启用热重载（文件变化自动重启）"
    )
    
    args = parser.parse_args()
    
    if args.command == "init":
        asyncio.run(init_project())
    
    elif args.command == "doctor":
        async def _doctor():
            doctor = Doctor(args.config)
            results = await doctor.run_all()
            exit_code = print_report(results)
            sys.exit(exit_code)
        asyncio.run(_doctor())
    
    elif args.command == "onboard":
        asyncio.run(run_onboarding())
    
    elif args.command == "worker":
        setup_logging(process_name=f"worker-{args.worker_type}", level="INFO")
        try:
            asyncio.run(run_worker_forever(args.worker_type, args.config))
        except KeyboardInterrupt:
            print(f"\n⛔ {args.worker_type} worker 已停止")
    
    elif args.command == "gateway":
        setup_logging(process_name="webhook", level="INFO")
        try:
            asyncio.run(run_worker_forever("webhook", args.config))
        except KeyboardInterrupt:
            print(f"\n⛔ webhook gateway 已停止")
    
    elif args.command == "server":
        setup_logging(process_name="api", level="INFO")
        try:
            asyncio.run(run_api_server(args.config, host=args.host, port=args.port))
        except KeyboardInterrupt:
            print(f"\n⛔ API Server 已停止")
    
    elif args.command == "run":
        setup_logging(process_name="tent-os", level="INFO")
        async def _run():
            tent = TentOS(args.config)
            await tent.start()
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
            finally:
                await tent.shutdown()
        
        if args.reload:
            print("🔥 热重载模式已启用，监控 tent_os/ 目录...")
            try:
                asyncio.run(run_with_reload(_run))
            except KeyboardInterrupt:
                print("\n⛔ Tent OS 已停止")
        else:
            try:
                asyncio.run(_run())
            except KeyboardInterrupt:
                print("\n⛔ Tent OS 已停止")
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
