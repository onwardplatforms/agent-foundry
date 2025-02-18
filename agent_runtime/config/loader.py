# import os
# import json
# from typing import Dict, Any, Optional
# from pathlib import Path
# from .hcl_loader import HCLConfigLoader


# class ConfigLoader:
#     @staticmethod
#     def load_config(
#         config_dir: str, config_file: Optional[str] = None
#     ) -> Dict[str, Any]:
#         """
#         Load configuration from either JSON or HCL format.
#         If config_file is not specified, it will look for agent.hcl first, then agent.json
#         """
#         if config_file:
#             return ConfigLoader._load_specific_config(config_dir, config_file)

#         # Try HCL first, then fall back to JSON
#         try:
#             if os.path.exists(os.path.join(config_dir, "agent.hcl")):
#                 return ConfigLoader._load_hcl_config(config_dir)
#             elif os.path.exists(os.path.join(config_dir, "agent.json")):
#                 return ConfigLoader._load_json_config(config_dir)
#             else:
#                 raise FileNotFoundError("No configuration file found")
#         except Exception as e:
#             raise Exception(f"Error loading configuration: {str(e)}")

#     @staticmethod
#     def _load_specific_config(config_dir: str, config_file: str) -> Dict[str, Any]:
#         file_path = os.path.join(config_dir, config_file)
#         if not os.path.exists(file_path):
#             raise FileNotFoundError(f"Configuration file not found: {file_path}")

#         if config_file.endswith(".hcl"):
#             return ConfigLoader._load_hcl_config(config_dir, config_file)
#         elif config_file.endswith(".json"):
#             return ConfigLoader._load_json_config(config_dir, config_file)
#         else:
#             raise ValueError("Unsupported configuration file format")

#     @staticmethod
#     def _load_json_config(
#         config_dir: str, config_file: str = "agent.json"
#     ) -> Dict[str, Any]:
#         """Load configuration from JSON format"""
#         config_path = os.path.join(config_dir, config_file)
#         with open(config_path, "r") as f:
#             return json.load(f)

#     @staticmethod
#     def _load_hcl_config(
#         config_dir: str, config_file: str = "agent.hcl"
#     ) -> Dict[str, Any]:
#         """Load configuration from HCL format"""
#         loader = HCLConfigLoader(config_dir)
#         return loader.load_config(config_file)
