with open('scratch/script3.js', 'r', encoding='utf-8', errors='ignore') as f:
    s3 = f.read()

pos = s3.find("36547:function")
print("=== Module 36547 ===")
print(s3[pos:pos+3000])
