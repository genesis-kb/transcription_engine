from setuptools import find_packages, setup


# Read the contents of the README file
with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()


# Function to read requirements from a file
def read_requirements(filename):
    return [
        line.strip()
        for line in open(filename)
        if line.strip() and not line.startswith("#")
    ]


# Read core requirements
install_requires = read_requirements("requirements.txt")

# Define extras and their requirements
extras_require = {
    "whisper": read_requirements("requirements-whisper.txt"),
}

# Add an "all" extra that includes all optional dependencies
extras_require["all"] = [
    req for reqs in extras_require.values() for req in reqs
]

setup(
    name="tstbtc",
    version="1.0.0",
    author="Andreas Kouloumos",
    author_email="kouloumosa@gmail.com",
    license="MIT",
    description="Transcribes audios and videos for bitcointranscripts",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/bitcointranscripts/tstbtc",
    py_modules=["transcriber", "server", "transcriber_server"],
    packages=find_packages(),
    install_requires=install_requires,
    extras_require=extras_require,
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "tstbtc=transcriber:cli",
            "tstbtc-server=transcriber_server:run",
        ],
    },
)
