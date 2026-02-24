---
inclusion: always
---

* Always favour to use query operations!
* Limit scan operations to the bare minimum and ask if you're in a situation where you want to use a scan operation
* Be careful with adding new GSI or LSI.
* Do not repurpose records. If you see the need to create a new record type explain it and ask for approval.
* Choose PK and SK in a way that belonging records can be queried easily.