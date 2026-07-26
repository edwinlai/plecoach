const CATEGORY_TOPIC = /^围绕“(.+)”聊一个真实生活场景$/;
const TARGET_WORDS_TOPIC = /^用“(.+)”聊聊你的经历$/;
const STORY_TOPIC = "一起编一个小故事，自然地用上今天的词";

export function translateConversationTopic(topic: string): string {
  const normalized = topic.trim();
  const categoryMatch = normalized.match(CATEGORY_TOPIC);
  if (categoryMatch) {
    return `Explore a real-life scenario around “${categoryMatch[1]}”.`;
  }

  const targetWordsMatch = normalized.match(TARGET_WORDS_TOPIC);
  if (targetWordsMatch) {
    return `Talk about your experience using “${targetWordsMatch[1]}”.`;
  }

  if (normalized === STORY_TOPIC) {
    return "Make up a short story using today’s words naturally.";
  }

  return "Discuss this topic in a natural Mandarin conversation.";
}
