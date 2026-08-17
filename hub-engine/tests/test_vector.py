from common.vector import cosine, vector


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