import pytest
from common.vector import build_idf, cosine, tokenize, vector

try:
    import jieba  # noqa: F401

    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False

skip_no_jieba = pytest.mark.skipif(not HAS_JIEBA, reason="jieba 未安装")


def test_vector_char_bigrams():
    v = vector("autocad dll")
    assert "au" in v and "oc" in v


def test_cosine_similar_sentences_high():
    a = vector("每次修改 DLL 后必须重命名版本号")
    b = vector("修改 DLL 后需要重命名版本号避免锁文件")
    assert cosine(a, b) > 0.3


def test_cosine_unrelated_low():
    a = vector("autocad dll version naming")
    b = vector("今天天气很好适合出去散步")
    assert cosine(a, b) < 0.1


def test_cosine_identity_is_one():
    a = vector("hello world hello world")
    assert cosine(a, a) == 1.0


@skip_no_jieba
def test_tokenize_word_mode_drops_stopwords():
    toks = tokenize("如何修改 DLL 并避免被锁", mode="word")
    assert "dll" in toks
    assert "如何" not in toks  # 停用词被过滤


@skip_no_jieba
def test_tokenize_word_mode_drops_punct_and_spaces():
    toks = tokenize("修改 DLL 后必须递增版本号。", mode="word")
    assert all("。" not in t and " " not in t for t in toks)


def test_tokenize_word_mode_falls_back_to_char(monkeypatch):
    monkeypatch.setattr("common.vector._has_jieba", lambda: False)
    toks = tokenize("autocad dll", mode="word")
    assert "au" in toks  # 无 jieba 回退字符 n-gram


@skip_no_jieba
def test_build_idf_weights_rare_tokens():
    docs = ["dll 版本号 递增", "dll 版本号 重命名", "机器人 webhook 配置"]
    idf = build_idf(docs, mode="word")
    assert "dll" in idf
    assert idf["webhook"] > idf["dll"]  # 罕见词 IDF 更高


@skip_no_jieba
def test_vector_idf_weights_rare_tokens():
    docs = ["dll 版本 递增", "dll 版本 重命名", "机器人 助手 配置"]
    idf = build_idf(docs, mode="word")
    v = vector("dll 机器人", mode="word", idf=idf)
    assert v["机器人"] > v["dll"]  # 罕见词加权后更重
