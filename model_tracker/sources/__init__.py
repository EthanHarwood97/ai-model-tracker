from . import aa_src, aider, deepswe, evalplus, gorilla, hf_openllm, livebench, lmarena, openrouter, swebench, tbench

SOURCES = {
    "aa_coding": aa_src.fetch_coding,
    "aa_models": aa_src.fetch_models,
    "aa_changelog": aa_src.fetch_changelog,
    "lmarena": lmarena.fetch,
    "livebench": livebench.fetch,
    "swebench": swebench.fetch,
    "aider": aider.fetch,
    "evalplus": evalplus.fetch,
    "hf_openllm": hf_openllm.fetch,
    "openrouter": openrouter.fetch,
    "tbench": tbench.fetch,
    "deepswe": deepswe.fetch,
    "gorilla": gorilla.fetch,
}
