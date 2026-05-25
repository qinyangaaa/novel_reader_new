from crawlers.universal_crawler import get_chapters
print('=== 单独测试 get_chapters ===')
ch = get_chapters('https://www.shuzhaige.com/doupocangqiong/')
print('章节数量:', len(ch))
for i, c in enumerate(ch[:20], 1):
    print(i, c)
