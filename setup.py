from setuptools import setup, find_packages

setup(
    name="queuectl",
    version="2.0.0",
    description="A production-grade CLI-based background job queue system with worker processes, "
                "retry logic, Dead Letter Queue, webhooks, and web dashboard",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="HARINARAYANAN U",
    author_email="hari.narayanan1402@gmail.com",
    url="https://github.com/IamHarriiii/Queuectl",
    packages=find_packages(),
    install_requires=[
        "click>=8.0.0",
        "requests>=2.28.0",
        "flask>=2.3.0",
        "flask-cors>=4.0.0",
        "flask-socketio>=5.3.0",
        "python-socketio>=5.9.0",
        "croniter>=1.3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "queuectl=queuectl.cli:cli",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Distributed Computing",
    ],
)