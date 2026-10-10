"""Generates a small self-created course (Intro to Machine Learning): textbook PDF (with a figure), slide deck PPTX (with a figure),
and a lecture transcript .vtt (timestamped). Run: python scripts/make_sample_course.py"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"; OUT.mkdir(exist_ok=True)
T = [
 ("Supervised Learning",
  "Supervised learning trains a model on labelled examples, where each input x is paired with a target output y. The goal is to learn a function f that predicts y for unseen inputs. Regression predicts a continuous value such as house price, while classification predicts a discrete label such as spam or not spam. The labelled dataset is split into a training set, used to fit the model, and a test set, used to measure generalisation.",
  ["Labelled data: inputs x paired with targets y", "Regression = continuous output; classification = discrete label"],
  "Think of supervised learning as studying with an answer key. You see many solved problems, and the model adjusts itself until its guesses match the answers. Then we hide a test set to check it really learned the pattern rather than memorising."),
 ("Linear Regression",
  "Linear regression models the target as a weighted sum of the inputs plus a bias term, y = w1x1 + w2x2 + b. The weights are chosen to minimise the mean squared error, the average of the squared differences between predictions and true values. For one feature the fitted model is a straight line through the data. The coefficient of determination R squared measures the fraction of variance explained by the model.",
  ["Prediction: y = w.x + b", "Loss: mean squared error (MSE)", "R squared = fraction of variance explained"],
  "Imagine fitting a straight line through a cloud of points. Each point that sits far from the line contributes a large squared error, so the line is pulled towards the points to keep the total error small."),
 ("Gradient Descent",
  "Gradient descent is an iterative optimisation algorithm that minimises a loss function. At each step the parameters move in the direction opposite to the gradient, scaled by the learning rate alpha: w = w - alpha times the gradient. If the learning rate is too large the updates overshoot and the loss diverges, whereas a very small learning rate converges slowly. Stochastic gradient descent estimates the gradient from a small mini-batch of 32 examples instead of the full dataset.",
  ["Update rule: w = w - alpha * gradient", "Learning rate too large -> divergence; too small -> slow", "SGD uses mini-batches"],
  "Picture standing on a foggy hill and wanting to reach the valley. You feel the slope under your feet and take a step downhill. The learning rate is the size of your step: giant leaps can carry you across the valley, tiny steps take forever."),
 ("Logistic Regression and Classification",
  "Logistic regression is a classification model that passes a linear score through the sigmoid function, sigma(z) = 1 / (1 + e^-z), to produce a probability between 0 and 1. A decision threshold, commonly 0.5, converts the probability into a class label. The model is trained by minimising the cross-entropy loss, also called log loss. The decision boundary is the set of points where the predicted probability equals the threshold.",
  ["Sigmoid squashes scores into probabilities", "Threshold 0.5 gives the class label", "Trained with cross-entropy loss"],
  "The sigmoid works like a dimmer switch rather than an on-off switch. A very negative score gives a probability near zero, a very positive score gives a probability near one, and zero maps to exactly one half."),
 ("Overfitting and Regularization",
  "Overfitting occurs when a model fits the noise in the training data and therefore performs poorly on new data. It is detected when training error is low but validation error is high. Regularization discourages complexity by adding a penalty to the loss: L2 regularization, also called ridge, penalises the sum of squared weights, while L1 regularization, called lasso, penalises the sum of absolute weights and can drive some weights exactly to zero. Cross-validation with 5 folds is a standard way to choose the regularization strength.",
  ["Overfitting: low training error, high validation error", "L2 (ridge) shrinks weights; L1 (lasso) creates sparsity", "Choose strength by cross-validation"],
  "An overfitted model is like a student who memorises last year's exam word for word. It scores perfectly on those questions but is lost when the wording changes. Regularization forces the student to learn general rules instead."),
 ("Bias-Variance Tradeoff",
  "The expected prediction error of a model decomposes into bias squared, variance, and irreducible noise. High bias means the model is too simple and underfits, missing real structure in the data. High variance means the model is too flexible and its predictions change greatly between different training sets, which is overfitting. Increasing model complexity lowers bias but raises variance, so the best generalisation lies at an intermediate complexity.",
  ["Error = bias^2 + variance + noise", "High bias -> underfitting; high variance -> overfitting"],
  "Imagine throwing darts. High bias means all darts land far from the bullseye in a tight cluster. High variance means the darts are scattered all over, even if their average is centred on the target."),
 ("Neural Networks and Backpropagation",
  "A neural network stacks layers of neurons, where each neuron computes a weighted sum of its inputs and applies a non-linear activation function such as ReLU, defined as max(0, z). Without non-linear activations a deep network would collapse into a single linear model. Backpropagation computes the gradient of the loss with respect to every weight by applying the chain rule backwards from the output layer to the input layer. These gradients are then used by gradient descent to update the weights.",
  ["Neuron: weighted sum + non-linear activation (ReLU)", "Backpropagation = chain rule applied layer by layer", "Gradients feed gradient descent"],
  "Backpropagation is blame assignment. The network makes a mistake at the output, and the chain rule tells us how much each earlier weight contributed to that mistake, so every weight can be nudged in the right direction."),
 ("Evaluation Metrics",
  "Accuracy is the fraction of correct predictions but is misleading on imbalanced data. Precision is the fraction of predicted positives that are truly positive, while recall is the fraction of actual positives that are found. The F1 score is the harmonic mean of precision and recall. For example, a classifier with precision 0.8 and recall 0.5 has an F1 score of about 0.62. The ROC curve plots the true positive rate against the false positive rate across thresholds.",
  ["Precision = TP / (TP + FP); recall = TP / (TP + FN)", "F1 = harmonic mean of precision and recall"],
  "If only one email in a hundred is spam, a lazy model that calls everything not-spam is ninety-nine percent accurate but useless. That is why we look at precision and recall, which focus on the rare class."),
 ("Clustering with K-Means",
  "K-means is an unsupervised algorithm that partitions data into k clusters. It starts by choosing k initial centroids, then alternates between assigning every point to its nearest centroid and recomputing each centroid as the mean of its assigned points. The algorithm stops when assignments no longer change. The result depends on initialisation and on the choice of k, which can be guided by the elbow method that plots within-cluster variance against k.",
  ["Unsupervised: no labels", "Assign to nearest centroid, then update centroids", "Elbow method helps choose k"],
  "Think of placing k flags on a map and letting every house join the nearest flag. Then you move each flag to the centre of its houses and repeat until nobody wants to switch."),
]


def figure(title, path, curve):
    im = Image.new("RGB", (640, 360), "white"); d = ImageDraw.Draw(im)
    try: f = ImageFont.load_default(size=26)
    except TypeError: f = ImageFont.load_default()
    d.text((20, 14), title, fill="black", font=f); d.line((60, 320, 600, 320), fill="black", width=3); d.line((60, 60, 60, 320), fill="black", width=3)
    d.text((300, 330), "iterations", fill="black", font=f); d.text((4, 40), "loss", fill="black", font=f)
    pts = [(60 + i * 18, 90 + int(220 * curve(i / 30))) for i in range(31)]; d.line(pts, fill="blue", width=4); im.save(path)


figure("Gradient descent: loss vs iterations", OUT / "fig_gd.png", lambda x: 1 - 0.95 * (1 - (1 - x) ** 3) if x < 1 else 0.05)
figure("Overfitting: training vs validation error", OUT / "fig_of.png", lambda x: 0.9 * (1 - x) ** 2 + 0.05)

import fitz
doc = fitz.open(); page = None; y = 0
def newpage():
    global page, y
    page = doc.new_page(); y = 60
for i, (name, para, _, _) in enumerate(T):
    if page is None or y > 560: newpage()
    page.insert_text((50, y), f"{i + 1}. {name}", fontsize=15, fontname="helv"); y += 12
    rc = fitz.Rect(50, y, 545, y + 150); page.insert_textbox(rc, para, fontsize=10.5, fontname="helv"); y += 165
    if name == "Gradient Descent": page.insert_image(fitz.Rect(150, y, 400, y + 140), filename=str(OUT / "fig_gd.png")); y += 150
    if name == "Overfitting and Regularization" and y < 560: page.insert_image(fitz.Rect(150, y, 400, y + 140), filename=str(OUT / "fig_of.png")); y += 150
doc.save(OUT / "intro_ml_textbook.pdf")

from pptx import Presentation
from pptx.util import Inches
prs = Presentation()
for name, _, bullets, _ in T:
    s = prs.slides.add_slide(prs.slide_layouts[1]); s.shapes.title.text = name
    tf = s.placeholders[1].text_frame; tf.text = bullets[0]
    for b in bullets[1:]: tf.add_paragraph().text = b
    if name == "Gradient Descent": s.shapes.add_picture(str(OUT / "fig_gd.png"), Inches(5.5), Inches(4.2), width=Inches(3.8))
prs.save(OUT / "intro_ml_slides.pptx")

import re
def ts(t): return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:06.3f}"
lines, t = ["WEBVTT", ""], 0.0
for name, _, _, lec in T:
    sents = re.split(r"(?<=[.!?])\s+", f"Next topic: {name}. " + lec)
    for s in sents:
        d = 4 + len(s.split()) * 0.35; lines += [f"{ts(t)} --> {ts(t + d)}", s, ""]; t += d
(OUT / "intro_ml_lecture.vtt").write_text("\n".join(lines))
print("Sample course written to", OUT)
