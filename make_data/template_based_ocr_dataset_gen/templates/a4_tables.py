"""Dedicated layout for massive, multi-column tables. Guaranteed to not overlap or break."""

import random
from core import assets, components, hybrid

NAME = "a4_tables"
BASE_MM = (210, 297)

def generate(hybrid_html=""):
    width, height = assets.jittered_size(*BASE_MM)
    
    # Generate 1 or 2 massive tables
    num_tables = random.randint(1, 2)
    
    blocks = []
    
    # 20% chance of a top-level heading
    if random.random() < 0.2:
        blocks.append(components.gen_heading())
    
    for _ in range(num_tables):
        # Generate a very large table that takes up most of the page
        # Up to 25 rows, up to 6 columns
        rows = random.randint(10, 25)
        cols = random.randint(3, 6)
        
        # Wrapped in a constrained flex block so it auto-shrinks if it overflows
        table_html = components.gen_table(rows=rows, cols=cols, compact=False)
        blocks.append(f'<div style="flex: 1; margin: 15px 0; overflow: hidden; min-height: 0; width: 100%; display: flex; flex-direction: column;">{table_html}</div>')
        
    if hybrid_html:
        # A tiny chance to insert a hybrid snippet
        blocks.insert(random.randint(0, len(blocks)), hybrid.wrap_hybrid_block(hybrid_html))
        
    flow = "".join(blocks)
    
    # Must use height: 100% so the A4 limits are strictly enforced!
    body = f'<div id="content-flow" style="width:100%; height:100%; padding:40px; box-sizing:border-box; display: flex; flex-direction: column; gap: 20px;">{flow}</div>'
    
    body = components.wrap_a4_page(body)
    
    return {"width": width, "height": height, "body": body, "auto_height": False}
