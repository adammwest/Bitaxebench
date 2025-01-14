#!/usr/bin/env python3
import socket
import json
import threading
import os
import hashlib

# HOST = '127.0.0.1'
HOST = '0.0.0.0'
PORT = 4444

# this one gets found by bm1368s
with open('879008.json', 'r') as f:
    data = json.loads(f.read())

NOTIFY_PARAMS = data['notify']['params']

# Store the last suggested difficulty
last_suggested_difficulty = 1024

v_mask = 0x00000000
n_mask = 0x00000000


##############################################################################
# 3) Merkle & Hashing Helpers
##############################################################################
def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def double_sha256(data: bytes) -> bytes:
    return sha256(sha256(data))

def calculate_merkle_root(transaction_hashes):
    """
    Compute merkle root for a list of transaction hashes (big-endian hex).
    """
    tx_hashes = [bytes.fromhex(txid)[::-1] for txid in transaction_hashes]
    while len(tx_hashes) > 1:
        new_level = []
        for i in range(0, len(tx_hashes), 2):
            left = tx_hashes[i]
            right = tx_hashes[i+1] if i+1 < len(tx_hashes) else tx_hashes[i]
            new_level.append(double_sha256(left + right))
        tx_hashes = new_level
    return tx_hashes[0][::-1].hex()

def build_merkle_tree(transaction_hashes):
    """
    Build and return the Merkle tree as a list of levels (each level is a list of LE bytes).
    """
    level = [bytes.fromhex(txid)[::-1] for txid in transaction_hashes]
    tree = [level]
    while len(level) > 1:
        new_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i+1] if i+1 < len(level) else level[i]
            new_level.append(double_sha256(left + right))
        level = new_level
        tree.append(level)
    return tree

def get_merkle_branch(tree, index):
    """
    Extract the Merkle branch for the item at the given index (from the bottom level).
    Each sibling is kept as LE bytes.
    """
    branch = []
    for level in tree[:-1]:
        sibling_index = index ^ 1  # flip last bit
        if sibling_index < len(level):
            branch.append(level[sibling_index])
        index //= 2
    return branch

def format_merkle_branch(branch):
    """Format merkle branch from LE bytes to BE hex strings."""
    return [h.hex() for h in branch]

def verify_merkle_root(tx_hash_big_endian, merkle_branch_big_endian, expected_merkle_root, tx_index=0):
    """
    Verify the Merkle proof. Inputs are provided as big-endian hex (Stratum style).
    Returns (True/False, calculated_merkle_root).
    """
    current_hash = bytes.fromhex(tx_hash_big_endian)[::-1]  # convert to LE bytes

    for sibling_hex in merkle_branch_big_endian:
        # Convert sibling from BE hex to LE bytes
        sibling = bytes.fromhex(sibling_hex)
        if (tx_index % 2) == 0:
            combined = current_hash + sibling
        else:
            combined = sibling + current_hash
        current_hash = double_sha256(combined)
        tx_index //= 2

    calculated_root = current_hash[::-1].hex()  # back to BE hex
    return (calculated_root == expected_merkle_root, calculated_root)


##############################################################################
# 5) Stratum Helpers
##############################################################################
def reverse_hex_bytewise(hex_string):
    if len(hex_string) % 2 != 0:
        raise ValueError("Hex string length must be even.")
    byte_pairs = [hex_string[i:i+2] for i in range(0, len(hex_string), 2)]
    return ''.join(byte_pairs[::-1])

def int_to_hex_le(value, length_bytes=4):
    """Convert an integer to little-endian hex representation."""
    return value.to_bytes(length_bytes, 'little').hex()

def int_to_hex_be(value, length_bytes=4):
    """Convert an integer to big-endian hex representation."""
    return value.to_bytes(length_bytes, 'big').hex()

def reverse_4byte_words(hash_hex_64):
    """
    Convert a 64-char hex string (32-byte hash) into Stratum's
    reversed-4-byte-word order.
    """
    if len(hash_hex_64) != 64:
        raise ValueError("Hash must be 64 hex chars.")
    words = [hash_hex_64[i:i+8] for i in range(0, 64, 8)]
    reversed_words = [w[6:8] + w[4:6] + w[2:4] + w[0:2] for w in words]
    return "".join(reversed_words)

def reverse_hex_bytewise(hex_string):
    if len(hex_string) % 2 != 0:
        raise ValueError("Hex string length must be even.")
    # Split the string into pairs of two characters (bytes)
    byte_pairs = [hex_string[i:i+2] for i in range(0, len(hex_string), 2)]
    # Reverse the order of the byte pairs
    reversed_pairs = byte_pairs[::-1]
    # Join them back into a single hex string
    return ''.join(reversed_pairs)

def to_stratum_hex(hex_string):
    return reverse_hex_bytewise(reverse_4byte_words(hex_string))

def from_stratum_hex(hex_string):
    return reverse_4byte_words(reverse_hex_bytewise(hex_string))


##############################################################################
# 6) Parse a SegWit Coinbase & Produce Legacy Serialization
##############################################################################
def read_varint(data, offset=0):
    """
    Minimal varint decode. Returns (value, new_offset).
    """
    first = data[offset]
    if first < 0xfd:
        return first, offset + 1
    elif first == 0xfd:
        return int.from_bytes(data[offset+1:offset+3], 'little'), offset + 3
    elif first == 0xfe:
        return int.from_bytes(data[offset+1:offset+5], 'little'), offset + 5
    else:
        return int.from_bytes(data[offset+1:offset+9], 'little'), offset + 9

def encode_varint(i):
    """Minimal varint encoding."""
    if i < 0xfd:
        return bytes([i])
    elif i <= 0xffff:
        return b'\xfd' + i.to_bytes(2, 'little')
    elif i <= 0xffffffff:
        return b'\xfe' + i.to_bytes(4, 'little')
    else:
        return b'\xff' + i.to_bytes(8, 'little')

def parse_coinbase_and_strip_witness(coinbase_hex):
    """
    Parse a coinbase transaction (which may include SegWit) and return its legacy serialization.
    Returns (nonwitness_bytes, full_tx_bytes).
    """
    tx_bytes = bytes.fromhex(coinbase_hex)
    cursor = 0

    # 1) version (4 bytes)
    version = tx_bytes[cursor:cursor+4]
    cursor += 4

    # 2) Check for segwit marker+flag
    marker = tx_bytes[cursor] if cursor < len(tx_bytes) else None
    flag = tx_bytes[cursor+1] if (cursor+1) < len(tx_bytes) else None
    is_segwit = (marker == 0 and flag == 1)
    if is_segwit:
        cursor += 2

    # 3) input count (varint)
    in_count, cursor = read_varint(tx_bytes, cursor)

    # 4) prev_out (36 bytes)
    vin = tx_bytes[cursor:cursor+36]
    cursor += 36

    # 5) scriptSig length (varint) and scriptSig
    script_len, cursor = read_varint(tx_bytes, cursor)
    script_sig = tx_bytes[cursor:cursor+script_len]
    cursor += script_len

    # 6) sequence (4 bytes)
    sequence = tx_bytes[cursor:cursor+4]
    cursor += 4

    # 7) output count (varint)
    out_count, cursor = read_varint(tx_bytes, cursor)

    # 8) outputs
    outputs_start = cursor
    for _ in range(out_count):
        cursor += 8  # value (8 bytes)
        pk_len, cursor = read_varint(tx_bytes, cursor)
        cursor += pk_len
    outputs = tx_bytes[outputs_start:cursor]

    # 9) If segwit, skip witness data
    if is_segwit:
        witness_count, cursor = read_varint(tx_bytes, cursor)
        for _ in range(witness_count):
            item_len, cursor = read_varint(tx_bytes, cursor)
            cursor += item_len

    # 10) locktime (4 bytes)
    locktime = tx_bytes[cursor:cursor+4]
    cursor += 4

    nonwitness_bytes = (version +
                        encode_varint(in_count) +
                        vin +
                        encode_varint(script_len) +
                        script_sig +
                        sequence +
                        encode_varint(out_count) +
                        outputs +
                        locktime)
    return nonwitness_bytes, tx_bytes



def reconstruct_block_hash(
    coinb1_hex, enonce1_bytes, enonce2_hex, coinb2_hex,
    merkle_branch, prevhash_stratum, version_hex_be, ntime_hex_be, nbits_hex, nonce_hex_be
):
    """
    Reconstruct full block hash:
      1. Rebuild the coinbase transaction as: coinb1 + enonce1 + enonce2 + coinb2.
      2. Compute the legacy TXID (double-SHA of non-witness serialization).
      3. Rebuild the Merkle root (using the TXID and merkle branch).
      4. Assemble the block header and compute its double-SHA256.
    """
    coinb1_bytes = bytes.fromhex(coinb1_hex)
    coinb2_bytes = bytes.fromhex(coinb2_hex)
    enonce2_bytes = bytes.fromhex(enonce2_hex) if enonce2_hex else b""
    full_coinbase = coinb1_bytes + enonce1_bytes + enonce2_bytes + coinb2_bytes

    # Get legacy (non-witness) coinbase serialization and compute its TXID.
    nonwitness_bytes, _ = parse_coinbase_and_strip_witness(full_coinbase.hex())
    coinbase_txid_le = double_sha256(nonwitness_bytes)
    coinbase_txid_be_hex = coinbase_txid_le[::-1].hex()

    # Apply the Merkle branch (coinbase is at index 0, so we always hash as: current || sibling)
    current_hash = coinbase_txid_le
    for sibling_hex in merkle_branch:
        # Convert sibling from BE hex to LE bytes before concatenation.
        sibling_le = bytes.fromhex(sibling_hex)
        current_hash = double_sha256(current_hash + sibling_le)
    # Final merkle root in BE.
    merkle_root_be_hex = current_hash[::-1].hex()
    # For block header, keep merkle root in LE.
    merkle_root_le = current_hash

    # Use the previous block hash directly from node JSON.
    # (prevhash_stratum here is assumed to be the same as block_data["previousblockhash"])
    prevhash_le = bytes.fromhex(from_stratum_hex(prevhash_stratum))[::-1]

    # Process the version.
    # The mining.notify contained version already XORed with the mask,
    # so here we invert that XOR to obtain the original block version.
    version_le = bytes.fromhex(version_hex_be)[::-1]
    version_int = int.from_bytes(version_le, 'little') ^ 0x20000000
    version_le = version_int.to_bytes(4, 'little')

    ntime_le = bytes.fromhex(ntime_hex_be)[::-1]
    nonce_le = bytes.fromhex(nonce_hex_be)[::-1]
    bits_le = bytes.fromhex(nbits_hex)[::-1]

    block_header = (version_le +
                    prevhash_le +
                    merkle_root_le +
                    ntime_le +
                    bits_le +
                    nonce_le)
    block_hash_le = double_sha256(block_header)
    block_hash_be_hex = block_hash_le[::-1].hex()

    # Calculate difficulty for info.
    MAX_TARGET = 0xFFFF * (2 ** (8 * (0x1D - 3)))
    block_hash_num = int(block_hash_be_hex, 16)
    difficulty = MAX_TARGET / block_hash_num

    return {
        "coinbase_txid_be": coinbase_txid_be_hex,
        "merkle_root_be": merkle_root_be_hex,
        "block_hash_be": block_hash_be_hex,
        "difficulty": difficulty
    }

def reconstruct(notify, submit):
    """
    Shortcut for reconstructing the block hash from mining.notify and mining.submit parameters.
    """
    return reconstruct_block_hash(
        coinb1_hex=notify[2],
        enonce1_bytes=bytes([0x00, 0x00, 0x00, 0x00]),
        enonce2_hex=submit[2],
        coinb2_hex=notify[3],
        merkle_branch=notify[4],
        prevhash_stratum=notify[1],  # Now prevhash_stratum is simply the previous block hash as given by the node.
        version_hex_be=submit[5],
        ntime_hex_be=submit[3],
        nbits_hex=notify[6],
        nonce_hex_be=submit[4]
    )


def send_json(conn, obj):
    """Utility: encode JSON + newline, send over socket."""
    line = json.dumps(obj) + "\n"
    conn.sendall(line.encode('utf-8'))


def client_thread(conn, addr):
    """Handle a single Stratum client connection."""
    global last_suggested_difficulty
    print(f"[+] Miner connected from {addr}")
    buffer = b""
    try:
        while True:
            # Accumulate data until we have at least one JSON line
            data = conn.recv(1024)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                handle_stratum_request(conn, line)
                # If a difficulty was suggested, send mining.set_difficulty
                if last_suggested_difficulty is not None:
                    set_difficulty_msg = {
                        "id": None,
                        "method": "mining.set_difficulty",
                        "params": [last_suggested_difficulty]
                    }
                    send_json(conn, set_difficulty_msg)
                    print(f"[+] Sent mining.set_difficulty with difficulty: {last_suggested_difficulty}")
                    last_suggested_difficulty = None
    except ConnectionResetError:
        print(f"[-] Miner {addr} disconnected abruptly.")
    except Exception as e:
        print(f"[!] Exception with miner {addr}: {e}")
    finally:
        conn.close()
        print(f"[-] Miner disconnected from {addr}")


def handle_stratum_request(conn, line):
    """Parse a single JSON line and handle various Stratum methods."""
    global last_suggested_difficulty
    try:
        message = json.loads(line.decode('utf-8'))
    except json.JSONDecodeError:
        print("[!] Invalid JSON received:", line)
        return

    req_id = message.get("id")
    method = message.get("method")
    params = message.get("params", [])

    if method == "mining.subscribe":
        # Provide subscription info
        response = {
            "id": req_id,
            "result": [
                [
                    ["mining.set_difficulty", "bf"],
                    ["mining.notify", "bf"]
                ],
                "00000000",  # extranonce1
                8            # extranonce2_size
            ],
            "error": None
        }
        send_json(conn, response)
        print("[+] Handled mining.subscribe")

    elif method == "mining.suggest_difficulty":
        # Store the suggested difficulty for later use
        last_suggested_difficulty = params[0] if params else 1
        print(f"[+] Received mining.suggest_difficulty = {last_suggested_difficulty}")
        # Minimal "OK" response
        response = {
            "id": req_id,
            "result": True,
            "error": None
        }
        send_json(conn, response)

    elif method == "mining.authorize":
        # Typically "params" = [username, password]
        username = params[0] if len(params) > 0 else "unknown"
        print(f"[+] Authorizing user: {username}")
        response = {
            "id": req_id,
            "result": True,
            "error": None
        }
        send_json(conn, response)

        # After authorize, send a single mining.notify job
        notify_msg = {
            "id": None,
            "method": "mining.notify",
            "params": NOTIFY_PARAMS
        }
        send_json(conn, notify_msg)
        print("[+] Sent mining.notify job")

    elif method == "mining.configure":
        # The miner is telling the server to use version-rolling with a given mask
        print("[+] Received mining.configure:", params)
        response = {
            "id": req_id,
            "result": {
                "version-rolling": True,
                "version-rolling.mask": "ffffffff"
            },
            "error": None
        }
        send_json(conn, response)

    elif method == "mining.submit":
        global v_mask, n_mask
        # The miner found a share
        # format:
        # [+] Received mining.submit: ['bc1qaxeplus9dxnsqeyc0zdu4vy6zh67ujuzvmx7mz.nerdqaxe', 'job123', '000000000000000b', '67828a1d', '35de0912', '08b84000']
        nonce = int(params[4], 16)
        version = int(params[5], 16)
        n_mask = n_mask | nonce
        v_mask = v_mask | version



        print(f"[+] Received mining.submit: {params} n_mask: {n_mask:08x}, v_mask: {v_mask:08x}")
        print(json.dumps(reconstruct(NOTIFY_PARAMS, params)))

        response = {
            "id": req_id,
            "result": True,  # Accept unconditionally
            "error": None
        }
        send_json(conn, response)

    else:
        # All other calls are unknown
        print(f"[!] Unhandled method: {method}")
        response = {
            "id": req_id,
            "error": [20, f"Unknown method {method}", None],
            "result": None
        }
        send_json(conn, response)


def start_server(host=HOST, port=PORT):
    """Start the minimal Stratum-like server."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(5)
    print(f"[+] Stratum server listening on {host}:{port}")

    try:
        while True:
            conn, addr = sock.accept()
            threading.Thread(target=client_thread, args=(conn, addr), daemon=True).start()
    finally:
        sock.close()


if __name__ == "__main__":
    start_server()
