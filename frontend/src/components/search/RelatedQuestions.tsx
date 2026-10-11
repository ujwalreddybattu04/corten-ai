interface RelatedQuestionsProps {
    questions: string[];
    onSelect: (question: string) => void;
}

export default function RelatedQuestions({ questions, onSelect }: RelatedQuestionsProps) {
    if (questions.length === 0) return null;

    return (
        <div className="related-questions" id="related-questions">
            <h3 className="related-questions-title">Related</h3>
            <div className="related-questions-list">
                {questions.map((question, index) => (
                    <button
                        key={index}
                        className="related-question-item"
                        onClick={() => onSelect(question)}
                    >
                        {question}
                    </button>
                ))}
            </div>
        </div>
    );
}
