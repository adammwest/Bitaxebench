# test-stratum-server

**note: It has been tested with BM1368 only. It might not work with 1366 and probably doesn't with 1370.**<br/>
**note2: BitAxe and BitAxeHex won't find the block. BitAxe not because the 3rd ASIC will find it and BitAxeHex not because the chip-ID is set differently**<br/>

This minimum test Stratum server is for testing [NerdQaxes](https://github.com/shufps/qaxe) finding a block.

The Stratum job is designed to trigger the finding at the `extranonce2 == '00000000000000ff'`.

Example:
```
$ python3 test-server.py 
[+] Stratum server listening on 0.0.0.0:4444
[+] Miner connected from ('192.168.0.161', 51442)
[+] Handled mining.subscribe
[+] Sent mining.set_difficulty with difficulty: 1024
[+] Received mining.configure: [['version-rolling'], {'version-rolling.mask': 'ffffffff'}]
[+] Authorizing user: bc1qaxeplus9dxnsqeyc0zdu4vy6zh67ujuzvmx7mz.nerdqaxe
[+] Sent mining.notify job
[+] Received mining.suggest_difficulty = 1000
[+] Sent mining.set_difficulty with difficulty: 1000
...
[+] Received mining.submit: ['bc1qaxeplus9dxnsqeyc0zdu4vy6zh67ujuzvmx7mz.nerdqaxe', 'job123', '00000000000000fe', '67845470', '4204043a', '1ff92000'] n_mask: ffff0ffe, v_mask: 1fffe000
{"coinbase_txid_be": "388e621ad250ad66c02b3a9957d5eaee546fb8ef6b02bd12d12ff7c5e9d4246e", "merkle_root_be": "d1648a54bb93dfb2b86016691902fa5591e62ac6aeef34a4909aa4346616633d", "block_hash_be": "00000000002122090df6e386fc9c6116893b5e9b5d46b5889fe720dffac1f0ec", "difficulty": 1977.9403491599999}
[+] Received mining.submit: ['bc1qaxeplus9dxnsqeyc0zdu4vy6zh67ujuzvmx7mz.nerdqaxe', 'job123', '00000000000000ff', '67845470', '67560e74', '02666000'] n_mask: ffff0ffe, v_mask: 1fffe000
{"coinbase_txid_be": "5413320d00f3f874a2c9681a98f9ce6c9a74af6774b16eec11811b1f631cd321", "merkle_root_be": "9da79b29b8668e18bc4b1aff1be3f5833147a1208abb2b4d91372e286cc5cab9", "block_hash_be": "00000000000000000001988bff3686b058e8e196226cbe59e5b5dbcaf5396498", "difficulty": 176372654042012.44}
[+] Received mining.submit: ['bc1qaxeplus9dxnsqeyc0zdu4vy6zh67ujuzvmx7mz.nerdqaxe', 'job123', '0000000000000100', '67845470', '7e100a4c', '1fb62000'] n_mask: ffff0ffe, v_mask: 1fffe000
{"coinbase_txid_be": "1a0f7a5f12c8a1769a6c1a87d2a6479fdc22bdd6893ec205098e4ce8e4014cef", "merkle_root_be": "1198f5cc3335c72076095baa7e076710174da3bd53c363fea59c91b96999365c", "block_hash_be": "00000000000fc052b27374c76a735d8581c804836b2883a5c78fe969de37f763", "difficulty": 4160.619040816413}
...
```

On the `NerdQAxe+`:

Settings: `490MHz`, job interval `1200ms`

![image](https://github.com/user-attachments/assets/dd45f31f-5907-490e-a6e5-e37a5282f3ea)

in the log:
```
I (653231) SystemModule: FOUND BLOCK!!! 176372654042012.437500 > 110451907374649.515625
```


# The scripts

1. `scan_compatible_blocks.py` scans the blocks from a local bitcoin node for the requirements of nonce bits `0xffff0ffe` and version bits `0x1fffe000`. Even if such compatible block was found the nonce is not found in all case. This can be ASIC model dependant (the method how the ASIC generates nonces).
2. `create_notify_submit.py` generates a `json` file for the given block number.
3. `test-server.py` is the actual test Stratum server loading a json file with a valid `notify` and `submit`.






