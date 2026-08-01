# -*- coding: utf-8 -*-
import os
import requests
import base58
import json
import time
from urllib.parse import urlparse  # --- 引入 URL 解析库 ---

# --- 配置区 ---
DEFAULT_URLS_TO_FETCH = [
    "https://raw.githubusercontent.com/cmliu/cmliu/refs/heads/main/tvapi_config_json",  
    "https://raw.githubusercontent.com/666zmy/MoonTV/refs/heads/main/config.json", 
    "https://raw.githubusercontent.com/hafrey1/LunaTV-config/main/LunaTV-config.txt",
    "https://raw.githubusercontent.com/rapier15sapper/ew/refs/heads/main/test.json",
    "https://raw.githubusercontent.com/anaer/Meow/main/meow.json"  # TVBox 格式 (sites 字段), 约77个源
]

def load_source_urls():
    """
    读取上游源列表：优先使用环境变量 SOURCE_URLS（支持逗号或换行分隔），
    未设置时回退到默认列表，便于在不修改代码的情况下切换/增删上游。
    """
    env_urls = os.environ.get("SOURCE_URLS", "").strip()
    if env_urls:
        urls = [u.strip() for u in env_urls.replace(",", "\n").splitlines() if u.strip()]
        if urls:
            print(f"已从环境变量 SOURCE_URLS 加载 {len(urls)} 个上游源")
            return urls
    return DEFAULT_URLS_TO_FETCH

URLS_TO_FETCH = load_source_urls()

# --- 白名单配置 ---
ALLOWED_TOP_LEVEL_KEYS = {"cache_time", "api_site"}

OUTPUT_FILENAME = "config.json"
MAX_RETRIES = 3
RETRY_DELAY = 5

def convert_sites_to_api_site(sites):
    """
    将 TVBox 格式的 sites 列表转换为本项目 api_site 字典格式。
    仅保留 api 字段为 http(s) 链接的站点（排除 JS/规则类源），
    例: {"key": "xxx", "name": "非凡", "api": "https://..."} -> {key: {"name":..., "api":...}}
    """
    converted = {}
    for index, site in enumerate(sites):
        if not isinstance(site, dict):
            continue
        api_link = site.get("api")
        if not isinstance(api_link, str) or not api_link.startswith("http"):
            # 跳过 JS 规则、jar 包等非采集接口源
            continue
        site_key = site.get("key") or site.get("id") or f"site_list_{index}"
        converted[site_key] = {
            "name": site.get("name", site_key),
            "api": api_link
        }
    return converted

def fetch_and_decode_url(url):
    """
    从URL获取内容，智能判断是Base58还是明文JSON，然后解码/解析，并根据白名单进行过滤。
    """
    for attempt in range(MAX_RETRIES):
        try:
            print(f"正在尝试第 {attempt + 1}/{MAX_RETRIES} 次请求链接: {url}")
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'
            content = response.text.strip()
            
            if not content:
                print(f"警告: 从 {url} 获取的内容为空。")
                return None

            data = None
            try:
                print("...尝试将内容作为 Base58 解码...")
                decoded_bytes = base58.b58decode(content)
                decoded_string = decoded_bytes.decode('utf-8')
                data = json.loads(decoded_string)
                print("...成功将内容作为 Base58 解码。")
            except Exception:
                print("...Base58 解码失败，尝试直接作为明文 JSON 解析...")
                try:
                    data = json.loads(content)
                    print("...成功将内容作为明文 JSON 解析。")
                except json.JSONDecodeError as json_e:
                    print(f"错误: 内容既不是有效的Base58，也不是有效的JSON。错误信息: {json_e}")
                    return None
            
            print(f"成功解析链接内容: {url}")

            if isinstance(data, list):
                print("...检测到内容为列表(Array)格式，正在自动转换为字典格式...")
                converted_sites = {}
                for index, item in enumerate(data):
                    if isinstance(item, dict):
                        api_link = item.get("baseUrl") or item.get("api") or item.get("url")
                        
                        if api_link:
                            site_key = item.get("id") or item.get("key") or item.get("name") or f"site_list_{index}"
                            
                            converted_sites[site_key] = {
                                "name": item.get("name", site_key),
                                "api": api_link
                                # 在这里移除了强制写入空 detail 的逻辑，统交由后面的 main 模块处理
                            }
                
                if converted_sites:
                    data = {
                        "api_site": converted_sites
                    }
                    print(f"...成功从列表中提取并转换了 {len(converted_sites)} 个有效源。")
                else:
                    print("警告: 列表中未找到任何包含 'api', 'url' 或 'baseUrl' 字段的有效源。")
                    return None

            if isinstance(data, dict):
                filtered_data = {key: data[key] for key in ALLOWED_TOP_LEVEL_KEYS if key in data}

                # --- 新增: 支持 TVBox 格式的 sites 字段 ---
                # 例: Meow 仓库的 meow.json, 顶层无 api_site, 而是 sites 列表
                sites_list = data.get("sites")
                if isinstance(sites_list, list) and sites_list:
                    converted_sites = convert_sites_to_api_site(sites_list)
                    if converted_sites:
                        existing = filtered_data.get("api_site", {})
                        if not isinstance(existing, dict):
                            existing = {}
                        merged = dict(existing)
                        merged.update(converted_sites)
                        filtered_data["api_site"] = merged
                        print(f"...成功从 TVBox sites 字段转换了 {len(converted_sites)} 个有效源。")

                if not filtered_data:
                    print("警告: 解析后的内容中未找到白名单指定的键 (cache_time/api_site) 或可转换的 sites 字段。")
                    return None
                print(f"内容已按白名单过滤，保留键: {list(filtered_data.keys())}")
                return filtered_data
            else:
                print("警告: 解析后的内容不是一个可按键过滤的字典。")
                return None

        except requests.exceptions.RequestException as req_e:
            print(f"错误：请求链接失败: {req_e}")
        except Exception as e:
            print(f"错误: 处理来自 {url} 的内容时发生未知错误: {e}")
        
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
            
    print(f"错误: 在 {MAX_RETRIES} 次尝试后，仍然无法处理链接: {url}")
    return None

def main():
    """
    主执行函数
    """
    print("--- 开始更新配置文件 ---")
    clean_data_buffer = [content for url in URLS_TO_FETCH if (content := fetch_and_decode_url(url))]
    if not clean_data_buffer:
        print("错误: 所有链接内容均为空或无法按规则过滤，无法生成配置文件。")
        return
    print(f"\n过滤完成，共获得 {len(clean_data_buffer)} 组有效内容。准备提取 detail 字段并合并...")
    
    merged_api_sites = {}
    for item in clean_data_buffer:
        if "api_site" in item and isinstance(item.get("api_site"), dict):
            for key, value in item["api_site"].items():
                
                # ==========================================
                # --- 核心改动：全局统一自动提取 detail 字段 ---
                # ==========================================
                if isinstance(value, dict) and "api" in value:
                    api_url = value["api"]
                    try:
                        # 尝试解析 URL (例如把 http://abc.com/api.php 变成 http://abc.com)
                        parsed_uri = urlparse(api_url)
                        if parsed_uri.scheme and parsed_uri.netloc:
                            base_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
                            value["detail"] = base_url
                        else:
                            # 如果提取不出合法域名，给个空字符串兜底
                            value.setdefault("detail", "")
                    except Exception:
                        value.setdefault("detail", "")
                else:
                    # 对于根本没有 api 字段的异常字典，也给个空值保持格式统一
                    if isinstance(value, dict):
                        value.setdefault("detail", "")
                # ==========================================

                new_key = key
                counter = 2
                while new_key in merged_api_sites:
                    new_key = f"{key}_{counter}"
                    counter += 1
                if new_key != key:
                    print(f"发现重复键 '{key}'，已重命名为 '{new_key}'")
                merged_api_sites[new_key] = value

    first_valid_cache_time = next((item.get("cache_time") for item in clean_data_buffer if "cache_time" in item), 7200)
    final_config = {
        "cache_time": first_valid_cache_time,
        "api_site": merged_api_sites
    }
    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(final_config, f, indent=4, ensure_ascii=False)
        print(f"成功！所有内容已通过重命名方式完整写入文件: {OUTPUT_FILENAME}")
    except IOError as e:
        print(f"错误: 写入文件 {OUTPUT_FILENAME} 失败: {e}")
    print("--- 更新任务结束 ---")

if __name__ == "__main__":
    main()
