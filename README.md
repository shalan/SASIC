# SASIC - Sky130 Structured ASIC Toolchain
## 1. PROJECT OVERVIEW

### 1.1 Mission Statement
Develop a complete open-source tool (gen_fabric.py) that generates Sky130-based structured ASIC fabrics from JSON specifications, enabling rapid prototyping and low-volume production with 70-80% cost reduction and 2-4 week turnaround times.

### 1.2 Value Proposition
- **Cost Reduction:** 70-80% lower fabrication costs vs. full-custom ASIC
- **Time-to-Market:** 2-4 weeks vs. 12-20 weeks for traditional ASIC
- **Risk Mitigation:** Pre-characterized fabric eliminates yield uncertainty
- **Accessibility:** Open-source tools democratize ASIC design

### 1.3 Technical Approach
Pre-fabricate base wafers containing regular arrays of Sky130 standard cells with fixed power network (met1-met2). Custom designs require fabrication of only top 3 metal layers (met3-met5) and vias.


