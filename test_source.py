import os
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "sources.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)
import os
import sqlite3
from plugins.source_manager import discover_sources, health_check
from crawlers.universal_crawler import search, get_chapters, get_content

# 第一步：建数据库并写入网站
base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "database", "sources.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)

conn = sqlite3.connect(db_path)
conn.execute("""CREATE TABLE IF NOT EXISTS website_sources (
    id INTEGER PRIMARY KEY,
    base_url TEXT UNIQUE,
    search_pattern TEXT,
    is_active INTEGER DEFAULT 1,
    success_rate INTEGER DEFAULT 100,
    last_checked TEXT
)""")
for url in ["https://www.shuzhaige.com", "https://www.xbiquge.la"]:
    conn.execute("INSERT OR IGNORE INTO website_sources (base_url) VALUES (?)", (url,))
conn.commit()
conn.close()
print("数据库初始化完成")

# 第二步：测试搜索
print("\n=== 测试搜索 ===")
results = search("斗破苍穹")
print(f"找到 {len(results)} 个结果")
for r in results[:3]:
    print(f"  {r['title']} - {r['source']}")

# 第三步：测试章节列表
print("\n=== 测试章节列表 ===")
chapters = get_chapters("https://www.shuzhaige.com/0_94/")
print(f"找到 {len(chapters)} 章")
for c in chapters[:3]:
    print(f"  {c['index']}. {c['title']}")

# 第四步：测试正文
if chapters:
    print("\n=== 测试正文 ===")
    content = get_content(chapters[0]['url'])
    print(f"标题：{content['title']}")
    print(f"正文前100字：{content['content'][:100]}")