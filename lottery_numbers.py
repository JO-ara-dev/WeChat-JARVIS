import random
import sys
sys.stdout.reconfigure(encoding='utf-8')

print('='*50)
print('      随机中奖号码生成器 (双色球风格)')
print('     红球 1-33 | 蓝球 1-16')
print('='*50)

for i in range(1, 11):
    red_balls = sorted(random.sample(range(1, 34), 6))
    blue_ball = random.randint(1, 16)
    red_str = ' '.join(f'{n:02d}' for n in red_balls)
    print(f'  第{i:2d}注: 红球 {red_str}  蓝球 {blue_ball:02d}')

print('='*50)
print('  祝老大中大奖！！！')
print('='*50)
