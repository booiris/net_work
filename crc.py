def calculateCRC(data):
    crc = 0
    for dat in data:
        crc = (crc >> 8) | (crc << 8)
        crc ^= dat
        crc ^= (crc & 0xFF) >> 4
        crc ^= crc << 12
        crc ^= (crc & 0x00FF) << 5
        crc &= 0xFFFF
    return crc


data = [0x01, 0x08, 0x00, 0x93, 0x50, 0x2e, 0x42, 0x83, 0x3e, 0xf1, 0x3f, 0x48, 0xb5, 0x04, 0xbb]
data = b'123121412'
print(data[0:0])
print(type(format(calculateCRC(data), '04x')))
