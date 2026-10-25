"""Conservative, local signals for prioritizing automatic memory reflection.

These signals only schedule the existing model review. They never create a memory
or replace the model's relevance, attribution, or conflict checks.
"""

from __future__ import annotations

import re


def classify_important_memory(text: str) -> str:
    """Return a high-confidence scheduling reason, or an empty string.

    Args:
        text: Current user's message, excluding assistant replies and history.

    Returns:
        An explicit request, stable preference, correction, or agreement reason.
        Ambiguous chatter, questions, quoted examples, and hypotheticals return
        an empty string and remain eligible for the normal batched reflection.
    """
    message = str(text or "").strip()
    if not message or message.startswith(("/", ">", "```", "“", '"', "‘", "'")):
        return ""

    # A quotation or fictional example must not be treated as the speaker's fact.
    if re.search(
        r"(?:假如|假设|如果|假装|举个?例|例如|比方说|角色扮演|虚构|"
        r"(?:^|[。！？\n])\s*(?:示例|例句|翻译|转述)|"
        r"(?:他|她|别人|有人|小[\u4e00-\u9fff]{1,5})(?:说|告诉我))",
        message,
    ):
        return ""
    denial_text = re.sub(r"(?:不要|别)(?:忘记|忘了|记错|记混)", "", message)
    if re.search(
        r"(?:不要|别|不用|不必|无需|不想让你).{0,6}(?:记住|记下|记|保存)",
        denial_text,
    ):
        return ""
    explicit = re.search(
        r"(?:记住|记一下|记下来|记下|记好|记牢|别忘了|别忘记|不要忘记)[，,:：\s]*(.+)",
        message,
    )
    is_question = bool(re.search(r"[?？]|(?:难道|是否|能否|为什么|什么时候|怎么样|怎么办)", message))
    if explicit:
        payload = explicit.group(1).strip("。！!，,:： ")
        if not is_question and len(payload) >= 3:
            return "explicit_memory"
        # A polite request may end with a question mark but still contain a new
        # fact. Recall checks such as "你记住了吗" carry no new fact to prioritize.
        request_prefix = message[:explicit.start()]
        if is_question and (not request_prefix or re.search(r"(?:请|帮我|替我|给我|麻烦)", request_prefix)):
            payload = re.sub(r"(?:[，,]\s*)?(?:好吗|可以吗|行吗|好不好|吗|么)?[?？]+\s*$", "", payload)
            if not re.search(r"(?:什么|怎么|哪[个些种里]|是否|能否|记住了)", payload) and re.search(
                r"(?:我(?:平时|一直|通常|一般|很|最)?(?:叫|名叫|姓|只喝|只吃|不喝|不吃|喜欢|不喜欢|偏好|习惯)[^，。！？]{1,}|"
                r"我的(?:名字|昵称|生日|版本|开发环境)(?:是|叫|在|为)[^，。！？]{1,}|"
                r"(?:明天|明早|明晚|后天|周[一二三四五六日天]|星期[一二三四五六日天])"
                r".{0,12}(?:开会|开服|复习|学习|练习|联机|打牌|检查|备份|吃饭))",
                payload,
            ):
                return "explicit_memory"
    if is_question:
        return ""
    if re.search(r"(?:以后|今后|往后)(?:请)?(?:叫我|称呼我)[^，。！!\n]{1,16}", message):
        return "explicit_memory"

    # Uncertain plans and temporary wishes should wait for normal consolidation.
    if re.search(r"(?:可能|也许|或许|说不定|想试试|暂时|今天想|这次想)", message):
        return ""

    if re.search(
        r"(?:更正(?:一下)?|纠正(?:一下)?|之前(?:说错|记错)了|(?:不要|别)记错|不是.{1,30}而是)",
        message,
    ):
        if re.search(r"(?:我|我们|本群|这个群|服务器|项目|版本|昵称|名字)", message):
            return "correction"

    if re.search(r"(?:约好了|约定|说好了|定好了)", message) and re.search(
        r"(?:周[一二三四五六日天]|星期|明天|后天|\d{1,2}[月日号点时:]|[一二三四五六七八九十两]+点|每天|每周|开服|开会)",
        message,
    ):
        return "arrangement"
    if re.search(
        r"(?:以后|今后|从现在起|从此).{0,12}(?:本群|我们|这个群|服务器|项目).{0,12}(?:默认|统一|固定|约定)",
        message,
    ):
        return "arrangement"
    if (
        re.search(r"(?:以后|今后|从现在起)", message)
        and re.search(
            r"(?:每周[一二三四五六日天]|每星期[一二三四五六日天]|每天|每月\d{1,2}[号日])"
            r"(?:早上|上午|中午|下午|晚上|晚|凌晨)?[0-9一二三四五六七八九十两]{1,3}(?:点|时|[:：]\d{2})",
            message,
        )
        and re.search(r"(?:一起|我们)", message)
        and re.search(r"(?:复习|学习|练习|开服|开会|联机|打牌|玩|检查|整理|备份|训练|跑步|吃饭)", message)
        and not re.search(r"(?:想|希望|打算|考虑|准备)", message)
    ):
        return "arrangement"

    # Require a concrete preference object; generic affection and deictic replies
    # such as "我喜欢这个" otherwise cause a reflection on routine banter.
    preference = re.search(
        r"我(?:一直|平时|通常|一向|长期|一般|最|比较|更|特别|非常|很|只)?"
        r"(?:不)?(?:喜欢|爱喝|爱吃|偏爱|偏好|习惯)([^，。！!；;\n]+)",
        message,
    )
    if preference:
        value = preference.group(1).strip()
        if value and not re.match(r"(?:你|您|它|他|她|这|那)", value):
            return "stable_preference"
    if re.search(
        r"我(?:平时|一直|通常|一向|长期|一般|每天).{0,6}"
        r"(?:只喝|只吃|不喝|不吃|用|使用|喝|吃|玩)[^，。！!\n]{1,50}",
        message,
    ):
        return "stable_preference"
    if re.search(r"我(?:对[^，。！!\n]{1,20}过敏|有[^，。！!\n]{1,20}过敏)", message):
        return "stable_preference"
    return ""
