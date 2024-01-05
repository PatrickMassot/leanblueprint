import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="leanblueprint",
    version="0.0.2",
    author="Patrick Massot",
    description="Lean prover blueprint plasTeX plugin.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    package_data={'leanblueprint': ['static/*', 'Packages/*',
                                    'Packages/renderer_templates/*']},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent"],
    python_requires='>=3.5',
    install_requires=['plasTeX>=3.0', 'plastexdepgraph', 'plastexshowmore']
)
